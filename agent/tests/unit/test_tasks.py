import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.actions import (
    Action,
    ActionRequest,
    AnswerAction,
    AnswerRequest,
    ClarificationAction,
    ClarificationRequest,
    DirectAnswer,
    DirectAnswerRequest,
    ExistingTaskReference,
    NewActionProposal,
    PendingTaskProposal,
    ProposedAction,
    PythonAction,
    PythonRequest,
    RetryActionReference,
    SQLAction,
    SQLRequest,
    Task,
    TaskPrerequisite,
    TaskProposal,
)


TASK_ID = "00000000-0000-4000-8000-000000000001"
ACTION_IDS = [
    "00000000-0000-4000-8000-000000000002",
    "00000000-0000-4000-8000-000000000003",
    "00000000-0000-4000-8000-000000000004",
    "00000000-0000-4000-8000-000000000005",
    "00000000-0000-4000-8000-000000000006",
]
V1_ID = "123e4567-e89b-12d3-a456-426614174000"
OTHER_V1_ID = "123e4567-e89b-12d3-a456-426614174001"
CONSTRAINTS = {
    "metric_definitions": {},
    "filters": [],
    "date_windows": [],
    "analysis_timezone": None,
    "grain": None,
    "units": {},
}
BLOCK = {
    "block_id": "answer-1",
    "kind": "general_explanation",
    "spans": [{"kind": "text", "text": "A direct answer"}],
    "supports": [],
}
CANDIDATE = {
    "candidate_id": "candidate-1",
    "interpretation": "Use booked revenue",
    "basis_refs": [],
}
REQUESTS = [
    {
        "type": "sql",
        "objective": "Query revenue",
        "constraints": CONSTRAINTS,
        "table_ids": [V1_ID],
        "input_evidence_ids": [],
    },
    {
        "type": "python",
        "objective": "Model revenue",
        "constraints": CONSTRAINTS,
        "input_evidence_ids": [V1_ID],
        "required_outputs": ["evidence", "chart"],
    },
    {
        "type": "answer",
        "objective": "Explain revenue",
        "constraints": CONSTRAINTS,
        "evidence_ids": [V1_ID],
        "chart_artifact_ids": [],
    },
    {
        "type": "direct_answer",
        "basis": "knowledge",
        "evidence_ids": [],
        "chart_artifact_ids": [],
        "context_refs": [V1_ID],
        "blocks": [BLOCK],
    },
    {
        "type": "clarify",
        "issue": "Revenue is ambiguous",
        "candidate_interpretations": [CANDIDATE],
        "constraints": CONSTRAINTS,
        "input_evidence_ids": [V1_ID],
        "context_refs": [],
    },
]
REQUEST_MODELS = [
    SQLRequest,
    PythonRequest,
    AnswerRequest,
    DirectAnswerRequest,
    ClarificationRequest,
]
ACTION_MODELS = [SQLAction, PythonAction, AnswerAction, DirectAnswer, ClarificationAction]
ACTIONS = [
    {**request, "action_id": action_id}
    for request, action_id in zip(REQUESTS, ACTION_IDS, strict=True)
]
PREREQUISITE = {"action_id": V1_ID, "expected_attempt": 1}


@pytest.mark.parametrize("payload,model", list(zip(REQUESTS, REQUEST_MODELS, strict=True)))
def test_every_action_request_round_trips_without_runtime_identity(payload, model):
    adapter = TypeAdapter(ActionRequest)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert result.model_dump() == payload
    assert adapter.validate_json(json.dumps(payload)) == result
    assert "action_id" not in result.model_fields_set


@pytest.mark.parametrize("payload,model", list(zip(ACTIONS, ACTION_MODELS, strict=True)))
def test_every_committed_action_remains_compatible(payload, model):
    adapter = TypeAdapter(Action)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert result.model_dump() == payload
    assert adapter.validate_json(json.dumps(payload)) == result


@pytest.mark.parametrize("payload,model", list(zip(REQUESTS, REQUEST_MODELS, strict=True)))
@pytest.mark.parametrize("field,value", [
    ("action_id", ACTION_IDS[0]),
    ("owner", "supervisor"),
    ("budget", 5),
    ("workspace_path", "C:/trusted"),
])
def test_requests_reject_runtime_owned_and_other_extra_fields(payload, model, field, value):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**payload, field: value})


@pytest.mark.parametrize("payload,model", list(zip(ACTIONS, ACTION_MODELS, strict=True)))
def test_committed_actions_still_require_runtime_uuid4(payload, model):
    missing = deepcopy(payload)
    del missing["action_id"]
    with pytest.raises(ValidationError, match="Field required"):
        model.model_validate(missing)
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "action_id": V1_ID})


TASKS = [
    {
        "task_id": TASK_ID,
        "type": "analysis",
        "requires": [PREREQUISITE],
        "actions": ACTIONS[:2],
    },
    {
        "task_id": TASK_ID,
        "type": "answer",
        "requires": [],
        "actions": [ACTIONS[2]],
    },
    {
        "task_id": TASK_ID,
        "type": "clarify",
        "requires": [],
        "actions": [ACTIONS[4]],
    },
    {
        "task_id": TASK_ID,
        "type": "direct_answer",
        "requires": [],
        "actions": [ACTIONS[3]],
    },
]


@pytest.mark.parametrize("payload", TASKS)
def test_every_committed_task_form_round_trips(payload):
    result = Task.model_validate(payload)
    assert result.model_dump() == payload
    assert Task.model_validate_json(json.dumps(payload)) == result


def test_task_and_prerequisite_fields_are_explicit_and_extras_forbidden():
    for field in TASKS[0]:
        payload = deepcopy(TASKS[0])
        del payload[field]
        with pytest.raises(ValidationError, match="Field required"):
            Task.model_validate(payload)
    for field in PREREQUISITE:
        payload = deepcopy(PREREQUISITE)
        del payload[field]
        with pytest.raises(ValidationError, match="Field required"):
            TaskPrerequisite.model_validate(payload)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Task.model_validate({**TASKS[0], "owner": "runtime"})


@pytest.mark.parametrize("model,field", [
    (TaskPrerequisite, "expected_attempt"),
    (RetryActionReference, "failed_attempt"),
])
def test_attempts_are_strict_positive_safe_json_integers(model, field):
    payload = (
        PREREQUISITE
        if model is TaskPrerequisite
        else {
            "kind": "retry_action",
            "action_id": V1_ID,
            "failed_attempt": 1,
            "result_ref": OTHER_V1_ID,
        }
    )
    assert getattr(model.model_validate({**payload, field: 9007199254740991}), field) == 9007199254740991
    for invalid in (True, 0, -1, 1.0, "1", 9007199254740992):
        with pytest.raises(ValidationError):
            model.model_validate({**payload, field: invalid})


def test_task_rejects_invalid_action_arity_and_types():
    with pytest.raises(ValidationError, match="at most 2"):
        Task.model_validate({**TASKS[0], "actions": [ACTIONS[0], ACTIONS[1], {**ACTIONS[0], "action_id": ACTION_IDS[4]}]})
    with pytest.raises(ValidationError, match="only sql or python"):
        Task.model_validate({**TASKS[0], "actions": [ACTIONS[2]]})
    for task_type, wrong_actions in (
        ("answer", [ACTIONS[0]]),
        ("clarify", [ACTIONS[4], {**ACTIONS[4], "action_id": ACTION_IDS[0]}]),
        ("direct_answer", [ACTIONS[3], {**ACTIONS[3], "action_id": ACTION_IDS[0]}]),
    ):
        with pytest.raises(ValidationError, match="exactly one matching action"):
            Task.model_validate({**TASKS[1], "type": task_type, "actions": wrong_actions})


def test_task_rejects_duplicate_actions_prerequisites_and_own_edges():
    with pytest.raises(ValidationError, match="action_id values must be unique"):
        Task.model_validate({**TASKS[0], "actions": [ACTIONS[0], ACTIONS[0]]})
    duplicate_prerequisites = [PREREQUISITE, {**PREREQUISITE, "expected_attempt": 2}]
    with pytest.raises(ValidationError, match="prerequisite action_id values must be unique"):
        Task.model_validate({**TASKS[0], "requires": duplicate_prerequisites})
    with pytest.raises(ValidationError, match="own actions"):
        Task.model_validate({
            **TASKS[0],
            "requires": [{"action_id": ACTION_IDS[0], "expected_attempt": 1}],
        })
    with pytest.raises(ValidationError):
        Task.model_validate({**TASKS[0], "requires": [PREREQUISITE] * 5})


NEW_ACTIONS = [
    {"kind": "new_action", "action_key": f"action-{index}", "request": request}
    for index, request in enumerate(REQUESTS)
]
RETRY = {
    "kind": "retry_action",
    "action_id": V1_ID,
    "failed_attempt": 2,
    "result_ref": OTHER_V1_ID,
}
PROPOSALS = [
    {"kind": "new_task", "task_key": "analysis", "type": "analysis", "requires": [], "actions": NEW_ACTIONS[:2]},
    {"kind": "new_task", "task_key": "answer", "type": "answer", "requires": [PREREQUISITE], "actions": [NEW_ACTIONS[2]]},
    {"kind": "new_task", "task_key": "clarify", "type": "clarify", "requires": [], "actions": [NEW_ACTIONS[4]]},
    {"kind": "new_task", "task_key": "direct", "type": "direct_answer", "requires": [], "actions": [NEW_ACTIONS[3]]},
    {"kind": "new_task", "task_key": "analysis-retry", "type": "analysis", "requires": [], "actions": [RETRY]},
    {"kind": "new_task", "task_key": "answer-retry", "type": "answer", "requires": [], "actions": [RETRY]},
]


@pytest.mark.parametrize("payload", PROPOSALS)
def test_every_new_task_proposal_form_round_trips(payload):
    adapter = TypeAdapter(PendingTaskProposal)
    result = adapter.validate_python(payload)
    assert isinstance(result, TaskProposal)
    assert result.model_dump() == payload
    assert adapter.validate_json(json.dumps(payload)) == result


def test_every_proposed_action_and_existing_task_reference_round_trips():
    proposed_adapter = TypeAdapter(ProposedAction)
    for payload, model in ((NEW_ACTIONS[0], NewActionProposal), (RETRY, RetryActionReference)):
        result = proposed_adapter.validate_python(payload)
        assert isinstance(result, model)
        assert proposed_adapter.validate_json(json.dumps(payload)) == result
    existing = {"kind": "existing_task", "task_id": V1_ID}
    result = TypeAdapter(PendingTaskProposal).validate_python(existing)
    assert isinstance(result, ExistingTaskReference)
    assert result.model_dump() == existing


def test_proposal_fields_are_required_and_extras_forbidden():
    for field in PROPOSALS[0]:
        payload = deepcopy(PROPOSALS[0])
        del payload[field]
        with pytest.raises(ValidationError):
            TaskProposal.model_validate(payload)
    for payload, model in ((NEW_ACTIONS[0], NewActionProposal), (RETRY, RetryActionReference)):
        for field in payload:
            missing = deepcopy(payload)
            del missing[field]
            with pytest.raises(ValidationError):
                model.model_validate(missing)
        with pytest.raises(ValidationError, match="extra_forbidden"):
            model.model_validate({**payload, "owner": "supervisor"})


def test_proposals_enforce_type_arity_and_retry_rules():
    with pytest.raises(ValidationError, match="at most 2"):
        TaskProposal.model_validate({**PROPOSALS[0], "actions": [*NEW_ACTIONS[:2], RETRY]})
    with pytest.raises(ValidationError, match="only sql or python"):
        TaskProposal.model_validate({**PROPOSALS[0], "actions": [NEW_ACTIONS[2]]})
    with pytest.raises(ValidationError, match="matching request"):
        TaskProposal.model_validate({**PROPOSALS[1], "actions": [NEW_ACTIONS[0]]})
    for task_type in ("clarify", "direct_answer"):
        with pytest.raises(ValidationError, match="retry actions"):
            TaskProposal.model_validate({**PROPOSALS[2], "type": task_type, "actions": [RETRY]})
    with pytest.raises(ValidationError, match="exactly one action"):
        TaskProposal.model_validate({
            **PROPOSALS[1], "requires": [], "actions": [NEW_ACTIONS[2], RETRY],
        })


def test_proposals_reject_duplicate_local_keys_and_retry_references():
    duplicate_new = [NEW_ACTIONS[0], {**NEW_ACTIONS[1], "action_key": NEW_ACTIONS[0]["action_key"]}]
    with pytest.raises(ValidationError, match="action_key values must be unique"):
        TaskProposal.model_validate({**PROPOSALS[0], "actions": duplicate_new})
    duplicate_retry = [RETRY, {**RETRY, "failed_attempt": 3, "result_ref": V1_ID}]
    with pytest.raises(ValidationError, match="retry action_id values must be unique"):
        TaskProposal.model_validate({**PROPOSALS[0], "actions": duplicate_retry})


def test_proposals_reject_duplicate_prerequisites_and_own_retry_edges():
    duplicate_prerequisites = [PREREQUISITE, {**PREREQUISITE, "expected_attempt": 2}]
    with pytest.raises(ValidationError, match="prerequisite action_id values must be unique"):
        TaskProposal.model_validate({**PROPOSALS[0], "requires": duplicate_prerequisites})
    with pytest.raises(ValidationError, match="retry actions"):
        TaskProposal.model_validate({**PROPOSALS[4], "requires": [PREREQUISITE]})


def test_supplied_references_accept_canonical_non_v4_ids():
    assert TaskPrerequisite.model_validate(PREREQUISITE).action_id == V1_ID
    assert RetryActionReference.model_validate(RETRY).action_id == V1_ID
    assert ExistingTaskReference.model_validate({
        "kind": "existing_task", "task_id": V1_ID,
    }).task_id == V1_ID
