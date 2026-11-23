import pytest
from pydantic import ValidationError

from querivue_agent.contracts.inputs import SupervisorInput
from querivue_agent.contracts.state import ModelMessage, RunExecutionStatus, RunHandle, RunState


PROJECT = "00000000-0000-4000-8000-000000000001"
CHAT = "00000000-0000-4000-8000-000000000002"
RUN = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"
SNAPSHOT = "00000000-0000-4000-8000-000000000005"
OWNER = "00000000-0000-4000-8000-000000000006"
ACTION = "00000000-0000-4000-8000-000000000007"
RESULT = "00000000-0000-4000-8000-000000000008"
HASH = "a" * 64
DEADLINE = "2026-11-23T12:00:00Z"


def scope():
    return {"project_id": PROJECT, "chat_id": CHAT, "run_id": RUN, "eligible_dataset_ids": []}


def counters():
    item = {"limit": 10, "used": 0, "reserved": 0, "unknown_reserved": 0}
    return {name: item for name in (
        "physical_requests", "logical_invocations", "input_tokens", "output_tokens",
        "tool_calls", "query_executions", "dispatch_attempts", "active_milliseconds",
        "wall_milliseconds", "output_bytes", "output_files",
    )}


def budget():
    return {
        "scope": scope(), "revision": 0, "counters": counters(),
        "cost": {"limit": "1", "used": "0", "reserved": "0", "unknown_reserved": "0", "currency": "USD"},
        "protected_reserves": [],
    }


def fence():
    return {
        "scope": scope(), "subject_kind": "run", "subject_id": RUN, "owner_id": OWNER,
        "generation": 1, "attempt": 1, "expected_revision": 0, "lease_expires_at": DEADLINE,
    }


def supervisor():
    return SupervisorInput.model_validate({
        "role": "supervisor",
        "packet": {
            "packet_id": OWNER, "content_hash": HASH, "policy_version": "policy-1",
            "configuration_hash": HASH, "base_snapshot_id": SNAPSHOT,
            "selected_records": [], "dependencies": [], "coverage": [],
        },
        "scope": scope(),
        "conversation": {
            "snapshot_id": SNAPSHOT, "chat_id": CHAT, "cutoff_sequence": 0,
            "original_message": {
                "message_id": MESSAGE, "chat_id": CHAT, "sequence": 0,
                "text": "How many orders?", "content_hash": HASH,
            },
            "linked_replies": [], "context_records": [], "interpretation_records": [],
            "thread_index": [], "conflicts": [],
        },
        "controls": {
            "fence": fence(), "budget": budget(), "deadline": DEADLINE,
            "environment_manifest_id": None, "environment_version": None,
            "policy_version": "policy-1", "phase": "planning", "active_operation_id": None,
        },
        "pending_tasks": [], "current_task": None, "outcomes": [], "evidence": [],
        "charts": [], "catalog": [], "obligations": [], "gaps": [], "source_choices": [],
        "queue_revision": 0, "analysis_started": False,
    })


def execution():
    return RunExecutionStatus.model_validate({
        "phase": "planning", "fence": fence(), "budget": budget(), "deadline": DEADLINE,
        "run_revision": 0, "queue_revision": 0, "expected_attempts": {},
        "active_draft_ref": None, "active_review_ref": None, "active_question_ref": None,
        "analysis_started": False, "review_reservations": [],
    })


def test_run_state_has_exactly_nine_fields_and_round_trips():
    state = RunState(
        input={
            "run_id": RUN, "project_id": PROJECT, "chat_id": CHAT,
            "question": "How many orders?", "eligible_dataset_ids": [],
        },
        context=supervisor(), evidence={}, messages=[], pending_tasks=[], current_task=None,
        outcomes={}, execution_status=execution(), output=None,
    )
    assert set(RunState.model_fields) == {
        "input", "context", "evidence", "messages", "pending_tasks", "current_task",
        "outcomes", "execution_status", "output",
    }
    assert RunState.model_validate_json(state.model_dump_json()) == state
    with pytest.raises(ValidationError):
        RunState.model_validate({**state.model_dump(), "client": object()})


def test_model_message_captures_provider_text_without_executing_it():
    call = {
        "call_id": "call-1", "name": "execute_query",
        "arguments_json": '{"sql":"DROP TABLE x"}', "provider_signature": "signed",
    }
    message = ModelMessage(role="assistant", content=None, tool_calls=[call], tool_call_id=None)
    assert message.tool_calls[0].arguments_json == '{"sql":"DROP TABLE x"}'
    with pytest.raises(ValidationError):
        ModelMessage(role="user", content=None, tool_calls=[call], tool_call_id=None)


def test_run_handle_status_controls_result_reference():
    completed = RunHandle(
        run_id=RUN, status="completed", run_revision=1, result_ref=SNAPSHOT, reason=None,
    )
    assert completed.result_ref == SNAPSHOT
    with pytest.raises(ValidationError):
        RunHandle(run_id=RUN, status="running", run_revision=1, result_ref=SNAPSHOT, reason=None)


def test_outcome_map_is_keyed_by_action_not_immutable_result_reference():
    status = execution().model_copy(update={"expected_attempts": {ACTION: 1}})
    outcome = {
        "task_id": "00000000-0000-4000-8000-000000000009",
        "action_id": ACTION,
        "attempt": 1,
        "result_ref": RESULT,
        "result": {
            "status": "blocked", "explanation": "Need a source",
            "required_input": "Choose a source", "evidence_ids": [],
        },
        "evidence_ids": [], "chart_artifact_ids": [],
    }
    payload = {
        "input": {
            "run_id": RUN, "project_id": PROJECT, "chat_id": CHAT,
            "question": "How many orders?", "eligible_dataset_ids": [],
        },
        "context": supervisor(), "evidence": {}, "messages": [], "pending_tasks": [],
        "current_task": None, "outcomes": {ACTION: outcome},
        "execution_status": status, "output": None,
    }
    assert RunState.model_validate(payload).outcomes[ACTION].result_ref == RESULT
    with pytest.raises(ValidationError, match="action IDs"):
        RunState.model_validate({**payload, "outcomes": {RESULT: outcome}})
