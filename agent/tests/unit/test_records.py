import hashlib
import json
import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.records import (
    AdmissionReceipt,
    AnswerResult,
    ClarificationQuestionRecord,
    DeletionReceipt,
    DirectCandidate,
    EntryQuestionRecord,
    FinalCandidate,
    FinalResult,
    IngestTarget,
    IngestionOperation,
    IntakeAdmission,
    IntakeReceipt,
    LinkedReply,
    ModelCompletion,
    ModelRequest,
    ModelReservation,
    ModelUsage,
    NewRunTarget,
    NoticeResult,
    OperationBlocked,
    OperationDiagnostics,
    OperationFailed,
    OperationOutcome,
    OperationRequest,
    OperationSucceeded,
    PreparationAttempt,
    QueueReceipt,
    ResumeReceipt,
    ResumeRunTarget,
    RetirementProof,
    ReviewReservation,
    ReviewedCandidate,
    SandboxTicket,
)


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


H_A = "a" * 64
H_B = "b" * 64
T0 = "2026-11-24T10:00:00+05:30"
T1 = "2026-11-24T10:01:00+05:30"
T2 = "2026-11-24T10:02:00+05:30"


def scope(*, run: bool = True, chat: bool = True) -> dict:
    return {
        "project_id": uid(1),
        "chat_id": uid(2) if chat else None,
        "run_id": uid(3) if run else None,
        "eligible_dataset_ids": [uid(4)],
    }


def artifact(*, media_type: str = "application/json", sha256: str = H_A) -> dict:
    return {
        "artifact_id": uid(10),
        "storage_ref": uid(11),
        "media_type": media_type,
        "size_bytes": 42,
        "sha256": sha256,
        "environment_manifest_id": uid(12),
    }


def schema(name: str = "terminal") -> dict:
    return {"name": name, "version": "v1", "sha256": H_A, "artifact": artifact()}


def provider() -> dict:
    return {
        "provider": "google",
        "model_id": "model",
        "endpoint": "https://models.example.test/v1",
        "route": "primary",
        "account_tier": "free",
        "region": "global",
        "quota_identity": "quota-v1",
        "sdk_name": "sdk",
        "sdk_version": "1",
        "protocol_version": "v1",
        "tokenizer_version": "tok-v1",
        "tokenizer_build_hash": H_A,
        "rate_manifest_hash": H_B,
        "observed_revision": None,
        "max_context_tokens": 4096,
        "rates": [{"meter": "request", "unit_size": 1, "usd_per_unit": "0"}],
        "free_tier_enforced": True,
        "accounting_verified": True,
        "privacy_verified": True,
    }


def inference() -> dict:
    return {
        "reasoning": None,
        "temperature": None,
        "seed": None,
        "max_generated_tokens": 512,
        "sampling_overrides_verified": False,
        "reasoning_in_output_budget": True,
    }


def message() -> dict:
    return {"role": "user", "content": "Question", "tool_calls": [], "tool_call_id": None}


def fence(value_scope: dict, *, kind: str = "run", subject_id: str | None = None) -> dict:
    return {
        "scope": value_scope,
        "subject_kind": kind,
        "subject_id": subject_id or value_scope["run_id"],
        "owner_id": uid(20),
        "generation": 1,
        "attempt": 1,
        "expected_revision": 0,
        "lease_expires_at": T2,
    }


def packet() -> dict:
    return {
        "packet_id": uid(21),
        "content_hash": H_A,
        "policy_version": "policy-v1",
        "configuration_hash": H_B,
        "base_snapshot_id": uid(22),
        "selected_records": [],
        "dependencies": [],
        "coverage": [],
    }


def entry_input() -> dict:
    text = "show upload instructions"
    return {
        "role": "entry",
        "packet": packet(),
        "scope": scope(run=False, chat=False),
        "input_kind": "upload_instructions",
        "submission_text": text,
        "submission_hash": hashlib.sha256(text.encode()).hexdigest(),
        "policy_version": "policy-v1",
        "linked_context": None,
        "followup_context": [],
        "cutoff_sequence": None,
    }


def counter_snapshot() -> dict:
    return {"limit": 100, "used": 0, "reserved": 0, "unknown_reserved": 0}


def budget(value_scope: dict) -> dict:
    names = [
        "physical_requests", "logical_invocations", "input_tokens", "output_tokens",
        "tool_calls", "query_executions", "dispatch_attempts", "active_milliseconds",
        "wall_milliseconds", "output_bytes", "output_files",
    ]
    return {
        "scope": value_scope,
        "revision": 0,
        "counters": {name: counter_snapshot() for name in names},
        "cost": {"limit": "1", "used": "0", "reserved": "0", "unknown_reserved": "0", "currency": "USD"},
        "protected_reserves": [],
    }


def tool(name: str) -> dict:
    return {"name": name, "schema": schema(name)}


def model_request(*, role: str = "sql", tools: list[dict] | None = None) -> dict:
    value_scope = scope(run=role != "entry", chat=role != "entry")
    expected = {
        "sql": ["inspect_table", "preview_rows", "inspect_evidence", "execute_query"],
        "python": ["inspect_evidence", "execute_python"],
    }.get(role, [])
    return {
        "request_id": uid(30),
        "invocation_id": uid(31),
        "scope": value_scope,
        "role": role,
        "action_id": uid(32) if role in ("sql", "python") else None,
        "intake_id": uid(33) if role == "entry" else None,
        "attempt": 1,
        "invocation_key": "invocation-1",
        "packet_id": uid(34),
        "packet_hash": H_A,
        "configuration_hash": H_B,
        "provider": provider(),
        "inference": inference(),
        "messages": [message()],
        "tools": tools if tools is not None else [tool(name) for name in expected],
        "terminal_schema": schema(),
        "application_request": artifact(),
        "max_input_tokens": 1024,
        "created_at": T0,
    }


def model_usage() -> dict:
    return {
        "input_tokens": 100,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "cached_input_tokens": None,
        "cost_usd": None,
        "raw_usage_ref": None,
    }


def intake_receipt() -> dict:
    # Use the simpler IntakeEntryInput format (from contracts.entry)
    entry = {
        "project_id": uid(1),
        "chat_id": uid(2),
        "question": "show upload instructions",
        "eligible_dataset_ids": [uid(4)],
    }
    # Scope for fence (without question)
    scope_for_fence = {
        "project_id": uid(1),
        "chat_id": uid(2),
        "run_id": None,
        "eligible_dataset_ids": [uid(4)],
    }
    import hashlib
    import json
    canonical = json.dumps(entry, separators=(",", ":"), sort_keys=True)
    submission_hash = hashlib.sha256(canonical.encode()).hexdigest()
    intake_id = uid(40)
    return {
        "intake_id": intake_id,
        "submission_key": "submission-1",
        "input": entry,
        "original_hash": submission_hash,
        "fence": fence(scope_for_fence, kind="intake", subject_id=intake_id),
        "entry_question_id": None,
        "outcome": None,
        "created_at": T0,
        "expires_at": T1,
        "status": "pending",
        "invocation_ids": [],
        "charge_ref": None,
    }


def admission(*, target: dict | None = None) -> dict:
    entry = entry_input()
    intake_id = uid(40)
    return {
        "admission_id": uid(41),
        "intake_id": intake_id,
        "submission_hash": entry["submission_hash"],
        "scope": entry["scope"],
        "assessment": {"disposition": "accept", "policy_reason": "allowed", "explanation": "Allowed"},
        "context_hash": H_A,
        "configuration_hash": H_B,
        "policy_version": "policy-v1",
        "target": target or {"kind": "new_run", "run_id": uid(3)},
        "fence": fence(entry["scope"], kind="intake", subject_id=intake_id),
        "accepted_at": T0,
    }


def constraints() -> dict:
    return {"metric_definitions": {}, "filters": [], "date_windows": [], "analysis_timezone": None, "grain": None, "units": {}}


def task() -> dict:
    return {
        "task_id": uid(50),
        "type": "analysis",
        "requires": [],
        "actions": [{
            "type": "sql",
            "objective": "Compute",
            "constraints": constraints(),
            "table_ids": [uid(51)],
            "input_evidence_ids": [],
            "action_id": uid(52),
        }],
    }


def review_request() -> dict:
    return {
        "review_id": uid(60),
        "draft_id": uid(61),
        "draft_content_hash": H_A,
        "draft_input_packet_hash": H_B,
        "rendering_policy_version": "render-v1",
        "review_pass": 1,
    }


def question() -> dict:
    return {"status": "question_ready", "question": {"spans": [{"kind": "text", "text": "Which range?"}], "supports": []}, "suggestions": []}


def source_dependency() -> dict:
    return {"dataset_id": uid(4), "snapshot_id": uid(70)}


def draft(*, unmet: bool = False) -> dict:
    return {
        "blocks": [{"block_id": "answer", "kind": "general_explanation", "spans": [{"kind": "text", "text": "Answer"}], "supports": []}],
        "unmet_deliverables": ([{"description": "Missing", "reason": "Unavailable", "required_evidence": "Source"}] if unmet else []),
    }


def reviewed_candidate(*, completeness: str = "complete") -> dict:
    review = {
        **review_request(),
        "review_input_packet_hash": "0" * 64,
        "status": "reviewed",
        "verdict": "approved",
        "findings": [],
    }
    return {
        "kind": "reviewed",
        "candidate_id": uid(62),
        "scope": scope(),
        "content_hash": H_A,
        "rendered_text": "Answer",
        "rendering_policy_version": "render-v1",
        "dependencies": [source_dependency()],
        "source_input_hash": H_B,
        "valid_until": T2,
        "originating_invocation_id": uid(63),
        "draft_id": uid(61),
        "draft": draft(unmet=completeness == "partial"),
        "completeness": completeness,
        "review": review,
        "approval_ref": uid(60),
    }


def direct_candidate() -> dict:
    return {
        "kind": "direct",
        "candidate_id": uid(64),
        "scope": scope(),
        "content_hash": H_A,
        "rendered_text": "Direct",
        "rendering_policy_version": "render-v1",
        "dependencies": [],
        "source_input_hash": H_B,
        "valid_until": T2,
        "originating_invocation_id": uid(65),
        "action": {
            "type": "direct_answer", "basis": "knowledge", "evidence_ids": [],
            "chart_artifact_ids": [], "context_refs": [],
            "blocks": [{"block_id": "direct", "kind": "general_explanation", "spans": [{"kind": "text", "text": "Direct"}], "supports": []}],
            "action_id": uid(66),
        },
        "completeness": "complete",
        "review_status": "not_required_direct",
    }


def import_settings(*, confirmed: bool) -> dict:
    selection = {
        "source": {"kind": "file", "format": "parquet"},
        "header_present": False,
        "header_row": None,
        "columns": [],
        "warnings": [],
    }
    value = {"settings_version": "v1", "source_format": "parquet", "selections": [selection], "dialect": None}
    if confirmed:
        selection["columns"] = [{
            "source_position": 0, "original_label": "value", "requested_type": {"tag": "string"},
            "missing_markers": [], "decimal_separator": None, "thousands_separator": None,
            "datetime_format": None, "source_timezone": None, "conversion_choice": None,
        }]
        value["confirmation_id"] = uid(80)
    return value


def resource_profile() -> dict:
    return {
        "cpu_millis": 1000, "memory_bytes": 1024, "filesystem_bytes": 4096,
        "scratch_bytes": 1024, "output_bytes": 1024, "output_files": 1,
        "network_disabled": True, "process_tree_limits_enforced": True,
        "isolation_profile_version": "v1",
    }


def tool_error() -> dict:
    return {"code": "python_execution_error", "message": "Failed", "stage": "execution", "operation_id": uid(90), "disposition": "correct_query"}


def operation_common(status: str) -> dict:
    return {
        "status": status,
        "operation_id": uid(90),
        "attempt": 1,
        "execution_generation": 1,
        "request_hash": H_A,
        "evidence": [],
        "charts": [],
        "diagnostics": {"stdout": "", "stderr": "", "stdout_truncated": False, "stderr_truncated": False, "source_dependencies": []},
        "completed_at": T1,
    }


@pytest.mark.parametrize(
    "model,payload",
    [
        (ModelRequest, model_request()),
        (ModelUsage, model_usage()),
        (ModelCompletion, {"completion_id": uid(35), "request_id": uid(30), "invocation_id": uid(31), "request_hash": H_A, "status": "completed", "response_artifact": artifact(), "provider_request_id": "provider-1", "observed_model_revision": None, "stop_reason": "stop", "usage": model_usage(), "error_ref": None, "recorded_at": T1}),
        (ModelReservation, {"reservation_id": uid(36), "scope": scope(), "request_id": uid(30), "invocation_id": uid(31), "role": "sql", "max_input_tokens": 1024, "max_output_tokens": 512, "cost_usd": "0.1", "admitted_at": T0, "expires_at": T1}),
        (NewRunTarget, {"kind": "new_run", "run_id": uid(3)}),
        (ResumeRunTarget, {"kind": "resume_run", "run_id": uid(3), "question_id": uid(37), "reply_ref": uid(38)}),
        (IngestTarget, {"kind": "ingest", "dataset_id": uid(4), "upload": artifact(media_type="application/octet-stream")}),
        (IntakeReceipt, intake_receipt()),
        (IntakeAdmission, admission()),
        (AdmissionReceipt, {"receipt_id": uid(42), "admission_id": uid(41), "intake_id": uid(40), "run_id": uid(3), "scope": scope(), "cutoff_sequence": 0, "budget": budget(scope()), "configuration_hash": H_B, "accepted_at": T0}),
        (QueueReceipt, {"receipt_id": uid(53), "run_id": uid(3), "invocation_id": uid(54), "proposal_hash": H_A, "decision_type": "propose_queue", "previous_queue_revision": 0, "queue_revision": 1, "run_revision": 1, "task_mapping": {"task-key": uid(50)}, "action_mapping": {"action-key": uid(52)}, "tasks": [task()], "withdrawn_task_ids": []}),
        (ReviewReservation, {"reservation_id": uid(67), "scope": scope(), "request": review_request(), "review_input_packet_hash": H_A, "fence": fence(scope()), "budget_reservation_id": uid(68), "reserved_at": T0, "deadline": T1, "max_physical_requests": 1, "max_input_tokens": 1000, "max_output_tokens": 500, "cost_usd": "0.1"}),
        (ClarificationQuestionRecord, {"question_id": uid(71), "scope": scope(), "action_id": uid(72), "attempt": 1, "owner_generation": 1, "slot": 1, "question": question(), "content_hash": H_A, "input_packet_id": uid(73), "input_packet_hash": H_B, "source_dependencies": [source_dependency()], "committed_at": T0, "expires_at": T1, "run_deadline": T2, "budget_reservation_id": uid(74)}),
        (EntryQuestionRecord, {"entry_question_id": uid(75), "intake_id": uid(40), "scope": entry_input()["scope"], "input": entry_input(), "question": "Which file?", "content_hash": H_A, "committed_at": T0, "expires_at": T1}),
        (LinkedReply, {"reply_id": uid(76), "run_id": uid(3), "question_id": uid(71), "entry_intake_id": uid(40), "submission_key": "reply-1", "message": {"message_id": uid(77), "chat_id": uid(2), "sequence": 2, "text": "Last 30 days", "content_hash": H_A}, "selected_option_ids": ["last-30"], "question_content_hash": H_B, "accepted_at": T0, "entry_admission_ref": uid(41)}),
        (ResumeReceipt, {"resume_id": uid(78), "run_id": uid(3), "question_id": uid(71), "reply_id": uid(76), "entry_intake_id": uid(40), "run_revision": 2, "owner_generation": 2, "accepted_at": T0, "original_deadline": T1, "scope": scope()}),
        (ReviewedCandidate, reviewed_candidate()),
        (DirectCandidate, direct_candidate()),
        (AnswerResult, {"kind": "answer", "result_id": uid(100), "scope": scope(), "route": "reviewed", "candidate_id": uid(62), "content_hash": H_A, "completeness": "complete", "rendered_text": "Answer", "rendering_policy_version": "render-v1", "evidence_ids": [uid(101)], "chart_artifact_ids": [], "dependencies": [source_dependency()], "published_at": T1, "review_status": "approved"}),
        (NoticeResult, {"kind": "notice", "result_id": uid(102), "scope": scope(), "status": "blocked", "reason_code": "source_unavailable", "rendered_text": "Source unavailable", "error_ref": None, "created_at": T1, "dependencies": []}),
        (DeletionReceipt, {"deletion_id": uid(103), "project_id": uid(1), "dataset_id": uid(4), "tombstone_revision": 1, "invalidated_run_ids": [uid(3)], "removed_result_ids": [], "deferred_artifact_ids": [], "retirement_pending_incarnation_ids": [], "committed_at": T1}),
        (SandboxTicket, {"ticket_id": uid(104), "scope": scope(), "sandbox_id": "sandbox-1", "command_id": None, "incarnation_id": uid(105), "action_id": uid(52), "operation_id": None, "attempt": 1, "generation": 1, "environment_manifest_id": uid(12), "state": "prepared", "created_at": T0, "expires_at": T1}),
        (RetirementProof, {"retirement_id": uid(106), "sandbox_id": "sandbox-1", "incarnation_id": uid(105), "confirmed_at": T1, "method": "process_tree_reaped", "process_tree_terminated": True, "proof_ref": uid(107), "environment_manifest_id": uid(12)}),
        (PreparationAttempt, {"dataset_id": uid(4), "attempt_id": uid(108), "attempt_number": 1, "settings": import_settings(confirmed=False), "settings_hash": H_A, "upload": artifact(media_type="application/octet-stream"), "upload_hash": H_A, "owner_generation": 1, "phase": "inspecting", "environment_manifest_id": None, "incarnation_id": None, "retirement_state": "not_started", "limits": None, "deadline": T2, "diagnostic_ref": None, "candidate_ref": None, "publication_ref": None}),
        (IngestionOperation, {"dataset_id": uid(4), "upload": artifact(media_type="application/octet-stream"), "settings": import_settings(confirmed=False)}),
        (OperationRequest, {"operation_id": uid(90), "scope": scope(), "task_id": uid(50), "action_id": uid(52), "attempt": 1, "execution_generation": 1, "invocation_key": "op-1", "request_hash": H_A, "kind": "sql_query", "request": {"sql": "select 1", "parameters": {}}, "input_artifacts": [], "deadline": T1, "environment_manifest_id": uid(12)}),
        (OperationDiagnostics, {"stdout": "ok", "stderr": "", "stdout_truncated": False, "stderr_truncated": False, "source_dependencies": []}),
        (OperationSucceeded, operation_common("succeeded")),
        (OperationFailed, {**operation_common("failed"), "error": tool_error()}),
        (OperationBlocked, {**operation_common("blocked"), "error": tool_error()}),
    ],
)
def test_record_families_round_trip_native_and_json(model, payload):
    result = model.model_validate(payload)
    assert result.model_dump() == payload
    assert model.model_validate_json(result.model_dump_json()) == result
    assert model.model_validate_json(json.dumps(payload)) == result


def test_discriminated_unions_round_trip_every_variant():
    candidate_adapter = TypeAdapter(FinalCandidate)
    result_adapter = TypeAdapter(FinalResult)
    operation_adapter = TypeAdapter(OperationOutcome)
    for payload in (reviewed_candidate(), direct_candidate()):
        value = candidate_adapter.validate_python(payload)
        assert candidate_adapter.validate_json(value.model_dump_json()) == value
    for payload in (
        {"kind": "answer", "result_id": uid(100), "scope": scope(), "route": "direct", "candidate_id": uid(64), "content_hash": H_A, "completeness": "complete", "rendered_text": "Direct", "rendering_policy_version": "v1", "evidence_ids": [], "chart_artifact_ids": [], "dependencies": [], "published_at": T1, "review_status": "not_required_direct"},
        {"kind": "notice", "result_id": uid(102), "scope": scope(), "status": "failed", "reason_code": "failed", "rendered_text": "Failed", "error_ref": uid(109), "created_at": T1, "dependencies": []},
    ):
        value = result_adapter.validate_python(payload)
        assert result_adapter.validate_json(value.model_dump_json()) == value
    for payload in (operation_common("succeeded"), {**operation_common("failed"), "error": tool_error()}, {**operation_common("blocked"), "error": tool_error()}):
        value = operation_adapter.validate_python(payload)
        assert operation_adapter.validate_json(value.model_dump_json()) == value


def test_model_request_role_tools_context_and_raw_request_are_bound():
    for role in ("sql", "python", "entry", "supervisor", "answer", "reviewer", "clarification"):
        ModelRequest.model_validate(model_request(role=role))
    with pytest.raises(ValidationError, match="tool declarations"):
        ModelRequest.model_validate(model_request(role="sql", tools=[tool("execute_query")]))
    payload = model_request(role="entry")
    payload["scope"] = scope(run=True, chat=True)
    with pytest.raises(ValidationError, match="entry request cannot carry run scope"):
        ModelRequest.model_validate(payload)
    payload = model_request()
    payload["application_request"] = artifact(media_type="text/plain")
    with pytest.raises(ValidationError, match="application request"):
        ModelRequest.model_validate(payload)
    payload = model_request()
    payload["max_input_tokens"] = 4000
    with pytest.raises(ValidationError, match="context"):
        ModelRequest.model_validate(payload)


def test_usage_preserves_unknown_and_checks_known_subtotals():
    usage = ModelUsage.model_validate(model_usage())
    assert usage.cached_input_tokens is None and usage.cost_usd is None
    with pytest.raises(ValidationError, match="reasoning_tokens"):
        ModelUsage.model_validate({**model_usage(), "reasoning_tokens": 21})
    with pytest.raises(ValidationError, match="cached_input_tokens"):
        ModelUsage.model_validate({**model_usage(), "cached_input_tokens": 101})


def test_completion_status_does_not_promote_unknown_or_failed_to_success():
    common = {"completion_id": uid(35), "request_id": uid(30), "invocation_id": uid(31), "request_hash": H_A, "provider_request_id": None, "observed_model_revision": None, "stop_reason": None, "usage": model_usage(), "recorded_at": T1}
    with pytest.raises(ValidationError, match="completed"):
        ModelCompletion.model_validate({**common, "status": "completed", "response_artifact": None, "error_ref": None})
    with pytest.raises(ValidationError, match="failed"):
        ModelCompletion.model_validate({**common, "status": "failed", "response_artifact": None, "error_ref": None})
    unknown = ModelCompletion.model_validate({**common, "status": "unknown", "response_artifact": None, "error_ref": None})
    assert unknown.status == "unknown"


def test_intake_hash_fence_waiting_question_and_expiry_are_structural():
    base = intake_receipt()
    for change, match in (
        ({"original_hash": H_B}, "submission hash"),
        ({"expires_at": T0}, "expiry"),
        ({"status": "waiting"}, "entry_question_id"),
    ):
        with pytest.raises(ValidationError, match=match):
            IntakeReceipt.model_validate({**base, **change})


def test_admission_and_receipt_scope_links_are_enforced():
    resume_scope = scope()
    value = admission(target={"kind": "resume_run", "run_id": uid(3), "question_id": uid(71), "reply_ref": uid(76)})
    value["scope"] = resume_scope
    value["fence"]["scope"] = resume_scope
    IntakeAdmission.model_validate(value)
    value["target"]["run_id"] = uid(999)
    with pytest.raises(ValidationError, match="resume target"):
        IntakeAdmission.model_validate(value)


def test_queue_receipt_revision_mapping_and_stop_shapes():
    base = {"receipt_id": uid(53), "run_id": uid(3), "invocation_id": uid(54), "proposal_hash": H_A, "decision_type": "propose_queue", "previous_queue_revision": 0, "queue_revision": 1, "run_revision": 1, "task_mapping": {"task-key": uid(50)}, "action_mapping": {"action-key": uid(52)}, "tasks": [task()], "withdrawn_task_ids": []}
    for change in (
        {"queue_revision": 0},
        {"task_mapping": {"task-key": uid(999)}},
        {"action_mapping": {"action-key": uid(999)}},
        {"withdrawn_task_ids": [uid(50)]},
    ):
        with pytest.raises(ValidationError):
            QueueReceipt.model_validate({**base, **change})
    stop = {**base, "decision_type": "stop", "queue_revision": 0, "task_mapping": {}, "action_mapping": {}, "tasks": []}
    assert QueueReceipt.model_validate(stop).tasks == []


def test_question_and_resume_time_windows_are_ordered():
    record = {"question_id": uid(71), "scope": scope(), "action_id": uid(72), "attempt": 1, "owner_generation": 1, "slot": 1, "question": question(), "content_hash": H_A, "input_packet_id": uid(73), "input_packet_hash": H_B, "source_dependencies": [], "committed_at": T0, "expires_at": T1, "run_deadline": T2, "budget_reservation_id": uid(74)}
    with pytest.raises(ValidationError):
        ClarificationQuestionRecord.model_validate({**record, "run_deadline": T0})
    resume = {"resume_id": uid(78), "run_id": uid(3), "question_id": uid(71), "reply_id": uid(76), "entry_intake_id": uid(40), "run_revision": 2, "owner_generation": 2, "accepted_at": T1, "original_deadline": T1, "scope": scope()}
    with pytest.raises(ValidationError, match="deadline"):
        ResumeReceipt.model_validate(resume)


def test_reviewed_candidate_binding_and_completeness_are_frozen():
    for change in (
        {"content_hash": H_B},
        {"source_input_hash": H_A},
        {"approval_ref": uid(999)},
        {"completeness": "partial"},
    ):
        with pytest.raises(ValidationError):
            ReviewedCandidate.model_validate({**reviewed_candidate(), **change})
    assert ReviewedCandidate.model_validate(reviewed_candidate(completeness="partial")).completeness == "partial"


def test_answer_route_review_status_and_source_dependencies_agree():
    base = {"kind": "answer", "result_id": uid(100), "scope": scope(), "route": "direct", "candidate_id": uid(64), "content_hash": H_A, "completeness": "complete", "rendered_text": "Direct", "rendering_policy_version": "v1", "evidence_ids": [], "chart_artifact_ids": [], "dependencies": [], "published_at": T1, "review_status": "not_required_direct"}
    for change in (
        {"completeness": "partial"},
        {"review_status": "approved"},
        {"evidence_ids": [uid(101)]},
    ):
        with pytest.raises(ValidationError):
            AnswerResult.model_validate({**base, **change})


@pytest.mark.parametrize("invalid", [1, 1.0, "true", None])
def test_retirement_proof_requires_real_true_boolean(invalid):
    payload = {"retirement_id": uid(106), "sandbox_id": "sandbox-1", "incarnation_id": uid(105), "confirmed_at": T1, "method": "provider_termination", "process_tree_terminated": invalid, "proof_ref": uid(107), "environment_manifest_id": uid(12)}
    with pytest.raises(ValidationError):
        RetirementProof.model_validate(payload)


def test_preparation_proposal_cannot_claim_prepared_or_ready_state():
    base = {"dataset_id": uid(4), "attempt_id": uid(108), "attempt_number": 1, "settings": import_settings(confirmed=False), "settings_hash": H_A, "upload": artifact(media_type="application/octet-stream"), "upload_hash": H_A, "owner_generation": 1, "phase": "preparing", "environment_manifest_id": uid(12), "incarnation_id": uid(105), "retirement_state": "active", "limits": resource_profile(), "deadline": T2, "diagnostic_ref": None, "candidate_ref": None, "publication_ref": None}
    with pytest.raises(ValidationError, match="confirmed settings"):
        PreparationAttempt.model_validate(base)
    ready = {**base, "settings": import_settings(confirmed=True), "phase": "ready", "candidate_ref": uid(109), "publication_ref": uid(110)}
    assert PreparationAttempt.model_validate(ready).phase == "ready"


def test_operation_kind_payload_and_analysis_scope_are_bound():
    base = {"operation_id": uid(90), "scope": scope(), "task_id": uid(50), "action_id": uid(52), "attempt": 1, "execution_generation": 1, "invocation_key": "op-1", "request_hash": H_A, "kind": "sql_query", "request": {"sql": "select 1", "parameters": {}}, "input_artifacts": [], "deadline": T1, "environment_manifest_id": uid(12)}
    with pytest.raises(ValidationError, match="kind"):
        OperationRequest.model_validate({**base, "kind": "python_code"})
    with pytest.raises(ValidationError, match="analysis operation"):
        OperationRequest.model_validate({**base, "task_id": None})
    ingestion = {"dataset_id": uid(4), "upload": artifact(media_type="application/octet-stream"), "settings": import_settings(confirmed=False)}
    with pytest.raises(ValidationError, match="confirmed settings"):
        OperationRequest.model_validate({**base, "kind": "ingestion_prepare", "request": ingestion, "task_id": None, "action_id": None, "scope": scope(run=False, chat=False)})


def test_diagnostics_are_utf8_bounded_and_truncation_flags_are_strict():
    base = {"stdout": "界" * 5461, "stderr": "", "stdout_truncated": True, "stderr_truncated": False, "source_dependencies": []}
    OperationDiagnostics.model_validate(base)
    with pytest.raises(ValidationError, match="16384"):
        OperationDiagnostics.model_validate({**base, "stdout": base["stdout"] + "界"})
    with pytest.raises(ValidationError):
        OperationDiagnostics.model_validate({**base, "stdout_truncated": 1})
