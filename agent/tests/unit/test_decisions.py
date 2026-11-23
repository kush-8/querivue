from copy import deepcopy
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.control import (
    BasisReference, InterpretationUpdate, ObligationCheck, ObligationCheckItem,
    ObligationUpdate, PartialAuthorization, ProposeQueue, StopDecision,
    SupervisorDecision, UserMessageBasis,
)


V1 = "123e4567-e89b-12d3-a456-426614174000"
V1_B = "123e4567-e89b-12d3-a456-426614174001"
V4 = "123e4567-e89b-42d3-a456-426614174000"
CONSTRAINTS = {
    "metric_definitions": {}, "filters": [], "date_windows": [],
    "analysis_timezone": None, "grain": None, "units": {},
}
BASIS = {"kind": "user_message", "message_id": V1, "start_byte": 0, "end_byte": 2, "quote": "é"}
SUPPORT = {"kind": "context", "context_ref": V1}
INTERPRETATION = {
    "key": "metric", "kind": "metric_definition", "text": "Booked revenue",
    "status": "user_stated", "scope": "run", "basis_refs": [BASIS],
    "supersedes_record_id": None,
}
CREATE = {
    "operation": "create", "obligation_key": "total", "obligation_ref": None,
    "description": "Report the total", "basis": BASIS, "revision_basis": None,
}
SUPPORTED = {
    "obligation_ref": V1, "status": "supported", "support_refs": [SUPPORT],
    "outcome_refs": [], "gap_refs": [], "task_keys": [], "task_refs": [],
    "explanation": "Supplied context supports it", "withdrawal_basis": None,
}
CHECK = {"items": [SUPPORTED]}
SQL_ACTION = {
    "kind": "new_action", "action_key": "sql-1",
    "request": {
        "type": "sql", "objective": "Compute total", "constraints": CONSTRAINTS,
        "table_ids": [V1], "input_evidence_ids": [],
    },
}
ANALYSIS_TASK = {
    "kind": "new_task", "task_key": "analysis-1", "type": "analysis",
    "requires": [], "actions": [SQL_ACTION],
}
ANSWER_ACTION = {
    "kind": "new_action", "action_key": "answer-1",
    "request": {
        "type": "answer", "objective": "Answer", "constraints": CONSTRAINTS,
        "evidence_ids": [V1], "chart_artifact_ids": [],
    },
}
ANSWER_TASK = {
    "kind": "new_task", "task_key": "answer-task", "type": "answer",
    "requires": [], "actions": [ANSWER_ACTION],
}
PROPOSE = {
    "type": "propose_queue", "expected_queue_revision": 0,
    "interpretation_updates": [INTERPRETATION], "obligation_updates": [CREATE],
    "obligation_check": None, "partial_authorization": None,
    "pending_tasks": [ANALYSIS_TASK],
}
STOP = {
    "type": "stop", "expected_queue_revision": 1, "reason_code": "cannot_complete",
    "gap_refs": [V1_B], "obligation_check": CHECK,
}


def test_user_message_basis_round_trip_and_utf8_byte_span():
    assert UserMessageBasis.model_validate(BASIS).model_dump() == BASIS
    assert UserMessageBasis.model_validate({**BASIS, "end_byte": 1, "quote": " "})
    for payload in (
        {**BASIS, "end_byte": 1}, {**BASIS, "end_byte": 0}, {**BASIS, "quote": ""},
        {**BASIS, "message_id": V4},
    ):
        if payload["message_id"] == V4:
            # Canonical supplied IDs may be any UUID version.
            assert UserMessageBasis.model_validate(payload)
        else:
            with pytest.raises(ValidationError):
                UserMessageBasis.model_validate(payload)


def test_basis_reference_discriminator_accepts_user_and_existing_support_targets():
    adapter = TypeAdapter(BasisReference)
    assert isinstance(adapter.validate_python(BASIS), UserMessageBasis)
    assert adapter.validate_python(SUPPORT).kind == "context"
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown"})


def test_interpretation_round_trip_and_user_stated_requires_user_basis():
    assert InterpretationUpdate.model_validate(INTERPRETATION).model_dump() == INTERPRETATION
    with pytest.raises(ValidationError, match="user message"):
        InterpretationUpdate.model_validate({**INTERPRETATION, "basis_refs": [SUPPORT]})
    assert InterpretationUpdate.model_validate({**INTERPRETATION, "status": "tentative", "basis_refs": []})
    with pytest.raises(ValidationError):
        InterpretationUpdate.model_validate({**INTERPRETATION, "text": "é" * 1025})


@pytest.mark.parametrize("operation", ["revise", "withdraw"])
def test_obligation_update_operation_shapes(operation):
    payload = {
        **CREATE, "operation": operation, "obligation_key": None,
        "obligation_ref": V1, "revision_basis": BASIS,
    }
    assert ObligationUpdate.model_validate(payload).model_dump() == payload
    with pytest.raises(ValidationError):
        ObligationUpdate.model_validate({**payload, "obligation_key": "wrong"})


def test_obligation_create_requires_key_without_ref_or_revision_basis():
    assert ObligationUpdate.model_validate(CREATE).model_dump() == CREATE
    for change in ({"obligation_key": None}, {"obligation_ref": V1}, {"revision_basis": BASIS}):
        with pytest.raises(ValidationError):
            ObligationUpdate.model_validate({**CREATE, **change})


@pytest.mark.parametrize(
    "status,changes",
    [
        ("supported", {}),
        ("missing", {"support_refs": [], "gap_refs": [V1_B]}),
        ("unresolved", {"support_refs": [], "gap_refs": [V1_B]}),
        ("explicitly_withdrawn_by_user", {"support_refs": [], "withdrawal_basis": BASIS}),
    ],
)
def test_obligation_check_item_round_trips_every_status(status, changes):
    payload = {**SUPPORTED, "status": status, **changes}
    assert ObligationCheckItem.model_validate(payload).model_dump() == payload


def test_obligation_check_status_invariants_and_uniqueness():
    with pytest.raises(ValidationError, match="support or outcome"):
        ObligationCheckItem.model_validate({**SUPPORTED, "support_refs": []})
    for status in ("missing", "unresolved"):
        with pytest.raises(ValidationError, match="gap_refs"):
            ObligationCheckItem.model_validate({**SUPPORTED, "status": status, "support_refs": []})
    with pytest.raises(ValidationError, match="withdrawal_basis"):
        ObligationCheckItem.model_validate({**SUPPORTED, "status": "explicitly_withdrawn_by_user", "support_refs": []})
    with pytest.raises(ValidationError, match="unique"):
        ObligationCheck.model_validate({"items": [SUPPORTED, SUPPORTED]})
    with pytest.raises(ValidationError, match="unique"):
        ObligationCheckItem.model_validate({**SUPPORTED, "outcome_refs": [V1, V1]})


def test_empty_obligation_projection_is_structurally_allowed():
    assert ObligationCheck.model_validate({"items": []}).items == []


def test_partial_authorization_requires_true_unique_refs_and_unmet_or_gap():
    payload = {
        "partial_answer_allowed": True, "reason": "Return supported portion",
        "unmet_obligation_refs": [V1], "gap_refs": [], "supporting_refs": [V1_B],
    }
    assert PartialAuthorization.model_validate(payload).model_dump() == payload
    with pytest.raises(ValidationError):
        PartialAuthorization.model_validate({**payload, "partial_answer_allowed": False})
    with pytest.raises(ValidationError, match="requires"):
        PartialAuthorization.model_validate({**payload, "unmet_obligation_refs": []})
    with pytest.raises(ValidationError, match="unique"):
        PartialAuthorization.model_validate({**payload, "supporting_refs": [V1_B, V1_B]})


@pytest.mark.parametrize("invalid", [1, 1.0, "true"])
def test_partial_authorization_rejects_truthy_non_bool_python_values(invalid):
    payload = {
        "partial_answer_allowed": invalid, "reason": "Return supported portion",
        "unmet_obligation_refs": [V1], "gap_refs": [], "supporting_refs": [],
    }
    with pytest.raises(ValidationError, match="boolean true"):
        PartialAuthorization.model_validate(payload)


@pytest.mark.parametrize("invalid_json", ["1", "1.0", '"true"'])
def test_partial_authorization_rejects_truthy_non_bool_json_values(invalid_json):
    payload = (
        '{"partial_answer_allowed":' + invalid_json
        + ',"reason":"Return supported portion","unmet_obligation_refs":["' + V1
        + '"],"gap_refs":[],"supporting_refs":[]}'
    )
    with pytest.raises(ValidationError, match="boolean true"):
        PartialAuthorization.model_validate_json(payload)


@pytest.mark.parametrize("payload,model", [(PROPOSE, ProposeQueue), (STOP, StopDecision)])
def test_supervisor_decision_variants_round_trip(payload, model):
    adapter = TypeAdapter(SupervisorDecision)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result


def test_decision_defaults_are_only_documented_shared_defaults():
    result = StopDecision.model_validate(STOP)
    assert result.interpretation_updates == []
    assert result.obligation_updates == []
    assert result.partial_authorization is None


def test_decisions_reject_unknown_missing_mixed_and_runtime_fields():
    adapter = TypeAdapter(SupervisorDecision)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "route"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "stop", "reason_code": "cannot_complete"})
    for field in ("pending_tasks", "route", "next_node", "runtime_budget", "owner_id"):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            StopDecision.model_validate({**STOP, field: []})


def test_proposal_uniqueness_is_across_entire_queue():
    second = deepcopy(ANALYSIS_TASK)
    second["task_key"] = "analysis-2"
    second["actions"][0]["action_key"] = "sql-2"
    assert ProposeQueue.model_validate({**PROPOSE, "pending_tasks": [ANALYSIS_TASK, second]})
    duplicate_action = deepcopy(second)
    duplicate_action["actions"][0]["action_key"] = "sql-1"
    with pytest.raises(ValidationError, match="action keys"):
        ProposeQueue.model_validate({**PROPOSE, "pending_tasks": [ANALYSIS_TASK, duplicate_action]})
    with pytest.raises(ValidationError, match="task keys"):
        ProposeQueue.model_validate({**PROPOSE, "pending_tasks": [ANALYSIS_TASK, ANALYSIS_TASK]})
    existing = {"kind": "existing_task", "task_id": V1}
    with pytest.raises(ValidationError, match="existing task"):
        ProposeQueue.model_validate({**PROPOSE, "pending_tasks": [existing, existing]})


def test_control_task_is_sole_and_requires_obligation_check():
    valid = {**PROPOSE, "pending_tasks": [ANSWER_TASK], "obligation_check": CHECK}
    assert ProposeQueue.model_validate(valid)
    with pytest.raises(ValidationError, match="control task"):
        ProposeQueue.model_validate({**valid, "obligation_check": None})
    with pytest.raises(ValidationError, match="control task"):
        ProposeQueue.model_validate({**valid, "pending_tasks": [ANSWER_TASK, ANALYSIS_TASK]})


def test_partial_authorization_only_with_sole_new_answer_task():
    partial = {
        "partial_answer_allowed": True, "reason": "Supported portion only",
        "unmet_obligation_refs": [V1], "gap_refs": [], "supporting_refs": [],
    }
    assert ProposeQueue.model_validate({
        **PROPOSE, "pending_tasks": [ANSWER_TASK], "obligation_check": CHECK,
        "partial_authorization": partial,
    })
    with pytest.raises(ValidationError, match="sole new answer"):
        ProposeQueue.model_validate({**PROPOSE, "partial_authorization": partial})


def test_update_keys_and_refs_are_unique_per_decision():
    with pytest.raises(ValidationError, match="interpretation keys"):
        ProposeQueue.model_validate({**PROPOSE, "interpretation_updates": [INTERPRETATION, INTERPRETATION]})
    with pytest.raises(ValidationError, match="created obligation"):
        ProposeQueue.model_validate({**PROPOSE, "obligation_updates": [CREATE, CREATE]})
    revise = {**CREATE, "operation": "revise", "obligation_key": None, "obligation_ref": V1, "revision_basis": BASIS}
    withdraw = {**revise, "operation": "withdraw"}
    with pytest.raises(ValidationError, match="revised obligation"):
        ProposeQueue.model_validate({**PROPOSE, "obligation_updates": [revise, withdraw]})


def test_stop_requires_check_forbids_partial_and_deduplicates_gaps():
    with pytest.raises(ValidationError, match="require obligation_check"):
        StopDecision.model_validate({**STOP, "obligation_check": None})
    partial = {
        "partial_answer_allowed": True, "reason": "x", "unmet_obligation_refs": [V1],
        "gap_refs": [], "supporting_refs": [],
    }
    with pytest.raises(ValidationError, match="cannot carry"):
        StopDecision.model_validate({**STOP, "partial_authorization": partial})
    with pytest.raises(ValidationError, match="unique"):
        StopDecision.model_validate({**STOP, "gap_refs": [V1_B, V1_B]})
