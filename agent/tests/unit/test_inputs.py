import hashlib

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.inputs import (
    AnswerInput, ClarificationInput, ContextRecord, EntryInput, PacketMetadata, PythonInput,
    ReviewInput, RevisionContext, RoleInput, RunInput, SQLInput, SupervisorInput, UserMessage,
)


PROJECT = "00000000-0000-4000-8000-000000000001"
CHAT = "00000000-0000-4000-8000-000000000002"
RUN = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"
SNAPSHOT = "00000000-0000-4000-8000-000000000005"
PACKET = "00000000-0000-4000-8000-000000000006"
HASH = "a" * 64
DATASET = "00000000-0000-4000-8000-000000000008"
SOURCE_SNAPSHOT = "00000000-0000-4000-8000-000000000009"
EVIDENCE = "00000000-0000-4000-8000-000000000010"
ARTIFACT = "00000000-0000-4000-8000-000000000011"
STORAGE = "00000000-0000-4000-8000-000000000012"
ENVIRONMENT = "00000000-0000-4000-8000-000000000013"
TASK = "00000000-0000-4000-8000-000000000014"
ACTION = "00000000-0000-4000-8000-000000000015"
REVIEW = "00000000-0000-4000-8000-000000000016"
DRAFT = "00000000-0000-4000-8000-000000000017"


def scope():
    return {"project_id": PROJECT, "chat_id": CHAT, "run_id": RUN, "eligible_dataset_ids": [DATASET]}


def packet():
    return {
        "packet_id": PACKET,
        "content_hash": HASH,
        "policy_version": "policy-1",
        "configuration_hash": HASH,
        "base_snapshot_id": SNAPSHOT,
        "selected_records": [],
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
        "coverage": [],
    }


def conversation():
    return {
        "snapshot_id": SNAPSHOT,
        "chat_id": CHAT,
        "cutoff_sequence": 0,
        "original_message": {
            "message_id": MESSAGE, "chat_id": CHAT, "sequence": 0,
            "text": "How many orders?", "content_hash": HASH,
        },
        "linked_replies": [], "context_records": [], "interpretation_records": [],
        "thread_index": [], "conflicts": [],
    }


def counters():
    value = {"limit": 10, "used": 0, "reserved": 0, "unknown_reserved": 0}
    return {name: value for name in (
        "physical_requests", "logical_invocations", "input_tokens", "output_tokens",
        "tool_calls", "query_executions", "dispatch_attempts", "active_milliseconds",
        "wall_milliseconds", "output_bytes", "output_files",
    )}


def controls():
    deadline = "2026-11-23T12:00:00Z"
    return {
        "fence": {
            "scope": scope(), "subject_kind": "run", "subject_id": RUN, "owner_id": PACKET,
            "generation": 1, "attempt": 1, "expected_revision": 0,
            "lease_expires_at": deadline,
        },
        "budget": {
            "scope": scope(), "revision": 0, "counters": counters(),
            "cost": {
                "limit": "1", "used": "0", "reserved": "0",
                "unknown_reserved": "0", "currency": "USD",
            },
            "protected_reserves": [],
        },
        "deadline": deadline, "environment_manifest_id": ENVIRONMENT,
        "environment_version": "env-1", "policy_version": "policy-1",
        "phase": "analysis", "active_operation_id": None,
    }


def constraints():
    return {
        "metric_definitions": {}, "filters": [], "date_windows": [],
        "analysis_timezone": None, "grain": None, "units": {},
    }


def evidence():
    column = {
        "ordinal": 0, "name": "amount", "original_label": "Amount",
        "original_ordinal": 0, "type": {"tag": "int64"}, "nullable": False,
    }


def shaped_evidence(index=0, *, rows=1, preview_columns=1):
    payload = evidence()
    payload["evidence_id"] = f"00000000-0000-4000-8000-{100 + index:012d}"
    payload["artifact"] = {
        **payload["artifact"],
        "artifact_id": f"00000000-0000-4000-8000-{200 + index:012d}",
        "storage_ref": f"00000000-0000-4000-8000-{300 + index:012d}",
    }
    columns = [
        {
            "ordinal": ordinal, "name": f"c{ordinal}", "original_label": f"C{ordinal}",
            "original_ordinal": ordinal, "type": {"tag": "int64"}, "nullable": False,
        }
        for ordinal in range(preview_columns)
    ]
    payload["columns"] = columns
    payload["row_count"] = rows
    payload["preview"] = {
        "columns": columns,
        "rows": [[str(row + column) for column in range(preview_columns)] for row in range(rows)],
        "row_locators": list(range(rows)), "full_row_count": rows,
        "returned_row_count": rows, "effective_limit": max(1, rows),
        "ordering": "unspecified", "truncated": False, "shortened_cells": [],
    }
    return payload


def chart(index=0):
    chart_id = f"00000000-0000-4000-8000-{400 + index:012d}"
    return {
        "chart_artifact_id": chart_id,
        "artifact": {
            "artifact_id": chart_id,
            "storage_ref": f"00000000-0000-4000-8000-{500 + index:012d}",
            "media_type": "image/png", "size_bytes": 1, "sha256": HASH,
            "environment_manifest_id": ENVIRONMENT,
        },
        "declaration": {
            "name": f"chart_{index}", "kind": "chart", "title": "Orders",
            "description": "Count", "series": [{
                "label": "Orders", "evidence_id": EVIDENCE, "ordering": [],
                "scales": {"y": "linear"}, "columns": {"x": "amount"},
            }],
            "units": {}, "analysis_timezone": None, "limitations": [],
        },
        "producer": {
            "kind": "python", "run_id": RUN, "action_id": ACTION,
            "operation_id": f"00000000-0000-4000-8000-{600 + index:012d}",
            "attempt": 1,
            "script_ref": f"00000000-0000-4000-8000-{700 + index:012d}",
            "script_hash": HASH, "input_evidence_ids": [EVIDENCE],
            "action_input_evidence_ids": [EVIDENCE], "constraints": constraints(),
            "random_seed": 0, "method_parameters": {},
            "environment_manifest_id": ENVIRONMENT, "policy_version": "policy-1",
        },
        "pixel_width": 100, "pixel_height": 100, "encoder_version": "1",
        "normalization_version": "1", "backing_evidence_ids": [EVIDENCE],
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
    }
    return {
        "evidence_id": EVIDENCE, "content_hash": HASH,
        "artifact": {
            "artifact_id": ARTIFACT, "storage_ref": STORAGE,
            "media_type": "application/vnd.apache.parquet", "size_bytes": 1,
            "sha256": HASH, "environment_manifest_id": ENVIRONMENT,
        },
        "columns": [column], "row_count": 1,
        "preview": {
            "columns": [column], "rows": [["1"]], "row_locators": [0],
            "full_row_count": 1, "returned_row_count": 1, "effective_limit": 1,
            "ordering": "unspecified", "truncated": False, "shortened_cells": [],
        },
        "producer": {
            "kind": "ingestion_profile", "dataset_id": DATASET,
            "snapshot_id": SOURCE_SNAPSHOT,
            "table_id": "00000000-0000-4000-8000-000000000018",
            "settings_hash": HASH, "profile_schema_version": "1",
            "environment_manifest_id": ENVIRONMENT,
        },
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
    }


def common(role):
    return {
        "role": role, "packet": packet(), "scope": scope(),
        "conversation": conversation(), "controls": controls(),
    }


def test_entry_input_round_trips_and_role_union_discriminates():
    text = "How many orders?"
    payload = {
        "role": "entry",
        "packet": packet(),
        "scope": scope(),
        "input_kind": "new_question",
        "submission_text": text,
        "submission_hash": hashlib.sha256(text.encode()).hexdigest(),
        "policy_version": "policy-1",
        "linked_context": None,
        "followup_context": [],
        "cutoff_sequence": 0,
    }
    entry = EntryInput.model_validate(payload)
    assert TypeAdapter(RoleInput).validate_json(entry.model_dump_json()) == entry

    with pytest.raises(ValidationError):
        EntryInput.model_validate({**payload, "role": "sql"})


def test_user_message_and_run_input_are_strict_and_preserve_question():
    message = UserMessage(
        message_id=MESSAGE, chat_id=CHAT, sequence=0, text="Café 世界", content_hash=HASH,
    )
    assert UserMessage.model_validate_json(message.model_dump_json()) == message
    assert RunInput(
        run_id=RUN, project_id=PROJECT, chat_id=CHAT,
        question=message.text, eligible_dataset_ids=[],
    ).question == "Café 世界"


def test_context_record_requires_user_basis_and_runtime_help_status():
    base = {
        "context_ref": "00000000-0000-4000-8000-000000000007",
        "kind": "metric_definition",
        "text": "Revenue means net sales.",
        "basis_refs": [],
        "dependencies": [],
        "scope": "run",
        "status": "user_stated",
    }
    with pytest.raises(ValidationError):
        ContextRecord.model_validate(base)
    with pytest.raises(ValidationError):
        ContextRecord.model_validate({**base, "kind": "help", "status": "tentative"})


def test_packet_metadata_rejects_duplicate_selected_record_identity():
    selected = {
        "record_id": MESSAGE,
        "content_hash": HASH,
        "revision": 0,
        "category": "message",
        "required": True,
    }
    with pytest.raises(ValidationError):
        PacketMetadata.model_validate({**packet(), "selected_records": [selected, selected]})


def test_every_analytical_role_round_trips_through_discriminated_union():
    sql = {
        **common("sql"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "sql", "action_id": ACTION, "objective": "Count orders",
            "constraints": constraints(), "table_ids": [], "input_evidence_ids": [EVIDENCE],
        },
        "tables": [], "evidence": [evidence()], "table_profiles": [],
    }
    python = {
        **common("python"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "python", "action_id": ACTION, "objective": "Count orders",
            "constraints": constraints(), "input_evidence_ids": [EVIDENCE],
            "required_outputs": ["evidence"],
        },
        "evidence": [evidence()],
    }
    answer = {
        **common("answer"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "answer", "action_id": ACTION, "objective": "Answer exactly",
            "constraints": constraints(), "evidence_ids": [EVIDENCE], "chart_artifact_ids": [],
        },
        "evidence": [evidence()], "charts": [], "obligations": [], "unmet_facts": [],
        "partial_authorization": None, "revision": None,
    }
    clarification = {
        **common("clarification"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "clarify", "action_id": ACTION, "issue": "Which window?",
            "candidate_interpretations": [], "constraints": constraints(),
            "input_evidence_ids": [], "context_refs": [],
        },
        "evidence": [], "obligations": [], "source_choices": [],
    }
    supervisor = {
        **common("supervisor"), "pending_tasks": [], "current_task": None,
        "outcomes": [], "evidence": [], "charts": [], "catalog": [],
        "obligations": [], "gaps": [], "source_choices": [],
        "queue_revision": 0, "analysis_started": False,
    }
    draft = {
        "blocks": [{
            "block_id": "answer", "kind": "general_explanation",
            "spans": [{"kind": "text", "text": "There is one order."}], "supports": [],
        }],
        "unmet_deliverables": [],
    }
    review = {
        **common("reviewer"),
        "request": {
            "review_id": REVIEW, "draft_id": DRAFT, "draft_content_hash": HASH,
            "draft_input_packet_hash": HASH, "rendering_policy_version": "render-1",
            "review_pass": 1,
        },
        "draft": draft, "rendered_text": "There is one order.",
        "draft_input": answer, "review_input_packet_hash": HASH,
    }

    models = [SQLInput, PythonInput, AnswerInput, ClarificationInput, SupervisorInput, ReviewInput]
    for payload, model in zip([sql, python, answer, clarification, supervisor, review], models, strict=True):
        value = TypeAdapter(RoleInput).validate_python(payload)
        assert isinstance(value, model)
        assert TypeAdapter(RoleInput).validate_json(value.model_dump_json()) == value


def test_required_selected_record_must_have_typed_packet_material():
    required_catalog = {
        "record_id": ARTIFACT, "content_hash": HASH, "revision": 0,
        "category": "catalog", "required": True,
    }
    payload = {
        **common("answer"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "answer", "action_id": ACTION, "objective": "Answer exactly",
            "constraints": constraints(), "evidence_ids": [EVIDENCE], "chart_artifact_ids": [],
        },
        "evidence": [evidence()], "charts": [], "obligations": [], "unmet_facts": [],
        "partial_authorization": None, "revision": None,
    }
    payload["packet"] = {**packet(), "selected_records": [required_catalog]}
    with pytest.raises(ValidationError):
        AnswerInput.model_validate(payload)


def test_packet_dependency_manifest_must_cover_supplied_evidence():
    payload = {
        **common("python"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "python", "action_id": ACTION, "objective": "Count orders",
            "constraints": constraints(), "input_evidence_ids": [EVIDENCE],
            "required_outputs": ["evidence"],
        },
        "evidence": [evidence()],
    }
    payload["packet"] = {**packet(), "dependencies": []}
    with pytest.raises(ValidationError, match="cover"):
        PythonInput.model_validate(payload)


def test_review_selection_resolves_frozen_draft_evidence():
    answer = {
        **common("answer"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "answer", "action_id": ACTION, "objective": "Answer exactly",
            "constraints": constraints(), "evidence_ids": [EVIDENCE], "chart_artifact_ids": [],
        },
        "evidence": [evidence()], "charts": [], "obligations": [], "unmet_facts": [],
        "partial_authorization": None, "revision": None,
    }
    selected = {
        "record_id": EVIDENCE, "content_hash": HASH, "revision": 0,
        "category": "evidence", "required": True,
    }
    review_packet = {**packet(), "selected_records": [selected]}
    review = {
        **common("reviewer"), "packet": review_packet,
        "request": {
            "review_id": REVIEW, "draft_id": DRAFT, "draft_content_hash": HASH,
            "draft_input_packet_hash": HASH, "rendering_policy_version": "render-1",
            "review_pass": 1,
        },
        "draft": {
            "blocks": [{
                "block_id": "answer", "kind": "general_explanation",
                "spans": [{"kind": "text", "text": "There is one order."}], "supports": [],
            }],
            "unmet_deliverables": [],
        },
        "rendered_text": "There is one order.", "draft_input": answer,
        "review_input_packet_hash": HASH,
    }
    assert ReviewInput.model_validate(review).draft_input.evidence[0].evidence_id == EVIDENCE


def test_entry_outcome_selection_requires_published_response_and_cutoff():
    text = "Continue"
    result_ref = "00000000-0000-4000-8000-000000000019"
    selection = {
        "record_id": result_ref, "content_hash": HASH, "revision": 0,
        "category": "outcome", "required": True,
    }
    followup = {
        "thread_id": RUN, "chat_id": CHAT, "sequence": 1, "result_ref": result_ref,
        "published_response": None, "description": "Prior result", "status": "tentative",
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
    }
    payload = {
        "role": "entry", "packet": {**packet(), "selected_records": [selection]},
        "scope": scope(), "input_kind": "new_question", "submission_text": text,
        "submission_hash": hashlib.sha256(text.encode()).hexdigest(),
        "policy_version": "policy-1", "linked_context": None,
        "followup_context": [followup], "cutoff_sequence": 1,
    }
    with pytest.raises(ValidationError, match="typed material"):
        EntryInput.model_validate(payload)

    followup["published_response"] = "The prior answer."
    assert EntryInput.model_validate(payload).followup_context[0].published_response == "The prior answer."
    with pytest.raises(ValidationError, match="cutoff"):
        EntryInput.model_validate({**payload, "cutoff_sequence": 0})
    cross_chat = {**followup, "chat_id": "00000000-0000-4000-8000-000000000020"}
    with pytest.raises(ValidationError, match="scoped chat"):
        EntryInput.model_validate({**payload, "followup_context": [cross_chat]})


def test_analytical_reply_lineage_is_explicit_and_packet_covered():
    text = "Use the first option"
    link = {
        "kind": "analytical_reply", "run_id": RUN,
        "question_id": "00000000-0000-4000-8000-000000000021",
        "original_question": "How many orders?",
        "pending_question": {
            "status": "question_ready",
            "question": {
                "spans": [{"kind": "text", "text": "Which source?"}], "supports": [],
            },
            "suggestions": [],
        },
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
    }
    payload = {
        "role": "entry", "packet": packet(), "scope": scope(),
        "input_kind": "analytical_reply", "submission_text": text,
        "submission_hash": hashlib.sha256(text.encode()).hexdigest(),
        "policy_version": "policy-1", "linked_context": link,
        "followup_context": [], "cutoff_sequence": 0,
    }
    assert EntryInput.model_validate(payload).linked_context.dependencies[0].dataset_id == DATASET
    with pytest.raises(ValidationError, match="cover"):
        EntryInput.model_validate({**payload, "packet": {**packet(), "dependencies": []}})


def test_revision_lineage_is_required_and_unique():
    revision = {
        "predecessor_draft_id": DRAFT,
        "previous_draft": {
            "blocks": [{
                "block_id": "answer", "kind": "general_explanation",
                "spans": [{"kind": "text", "text": "Old answer."}], "supports": [],
            }],
            "unmet_deliverables": [],
        },
        "review": {
            "status": "reviewed", "review_id": REVIEW, "draft_id": DRAFT,
            "draft_content_hash": HASH, "draft_input_packet_hash": HASH,
            "review_input_packet_hash": HASH, "rendering_policy_version": "render-1",
            "review_pass": 1, "verdict": "rejected",
            "findings": [{
                "finding_id": "finding", "category": "draft", "block_ids": ["answer"],
                "explanation": "Unsupported.", "support_refs": [],
                "required_change": "Add support.",
            }],
        },
        "dependencies": [{"dataset_id": DATASET, "snapshot_id": SOURCE_SNAPSHOT}],
    }
    assert RevisionContext.model_validate(revision).dependencies[0].dataset_id == DATASET
    with pytest.raises(ValidationError):
        RevisionContext.model_validate({**revision, "dependencies": revision["dependencies"] * 2})


def analysis_payload(role, views):
    base = {**common(role), "task_id": TASK, "attempt": 1}
    if role == "sql":
        return {
            **base,
            "request": {
                "type": "sql", "action_id": ACTION, "objective": "Count orders",
                "constraints": constraints(), "table_ids": [],
                "input_evidence_ids": [item["evidence_id"] for item in views],
            },
            "tables": [], "evidence": views, "table_profiles": [],
        }
    if role == "python":
        return {
            **base,
            "request": {
                "type": "python", "action_id": ACTION, "objective": "Count orders",
                "constraints": constraints(),
                "input_evidence_ids": [item["evidence_id"] for item in views],
                "required_outputs": ["evidence"],
            },
            "evidence": views,
        }
    raise AssertionError(role)


@pytest.mark.parametrize(("role", "model"), [("sql", SQLInput), ("python", PythonInput)])
def test_execution_role_preview_boundaries(role, model):
    accepted = analysis_payload(role, [shaped_evidence(rows=32, preview_columns=32)])
    assert len(model.model_validate(accepted).evidence[0].preview.rows) == 32

    too_many_rows = analysis_payload(role, [shaped_evidence(rows=33)])
    with pytest.raises(ValidationError, match="32 rows"):
        model.model_validate(too_many_rows)
    too_many_columns = analysis_payload(role, [shaped_evidence(preview_columns=33)])
    with pytest.raises(ValidationError, match="32 visible columns"):
        model.model_validate(too_many_columns)


def test_analysis_role_evidence_view_count_boundaries():
    eight = [shaped_evidence(index) for index in range(8)]
    nine = [shaped_evidence(index) for index in range(9)]
    assert len(PythonInput.model_validate(analysis_payload("python", eight)).evidence) == 8
    with pytest.raises(ValidationError):
        PythonInput.model_validate(analysis_payload("python", nine))

    combined = analysis_payload("sql", eight)
    combined["table_profiles"] = [shaped_evidence(8)]
    with pytest.raises(ValidationError, match="combined"):
        SQLInput.model_validate(combined)


def test_supervisor_view_and_chart_boundaries():
    payload = {
        **common("supervisor"), "pending_tasks": [], "current_task": None,
        "outcomes": [], "evidence": [shaped_evidence(rows=32, preview_columns=32)],
        "charts": [chart(index) for index in range(4)], "catalog": [],
        "obligations": [], "gaps": [], "source_choices": [],
        "queue_revision": 0, "analysis_started": False,
    }
    assert len(SupervisorInput.model_validate(payload).charts) == 4
    with pytest.raises(ValidationError):
        SupervisorInput.model_validate({**payload, "charts": [chart(index) for index in range(5)]})
    with pytest.raises(ValidationError, match="32 rows"):
        SupervisorInput.model_validate({**payload, "evidence": [shaped_evidence(rows=33)]})


def test_answer_view_boundaries_without_reviewer_shrink():
    view = shaped_evidence(rows=128, preview_columns=32)
    view["evidence_id"] = EVIDENCE
    payload = {
        **common("answer"), "task_id": TASK, "attempt": 1,
        "request": {
            "type": "answer", "action_id": ACTION, "objective": "Answer exactly",
            "constraints": constraints(), "evidence_ids": [EVIDENCE],
            "chart_artifact_ids": [item["chart_artifact_id"] for item in [chart(i) for i in range(4)]],
        },
        "evidence": [view], "charts": [chart(i) for i in range(4)],
        "obligations": [], "unmet_facts": [], "partial_authorization": None, "revision": None,
    }
    answer = AnswerInput.model_validate(payload)
    assert answer.evidence[0].preview.returned_row_count == 128
    too_large = shaped_evidence(rows=129, preview_columns=32)
    too_large["evidence_id"] = EVIDENCE
    with pytest.raises(ValidationError, match="128 rows"):
        AnswerInput.model_validate({**payload, "evidence": [too_large]})
    with pytest.raises(ValidationError):
        AnswerInput.model_validate({**payload, "charts": [chart(i) for i in range(5)]})
