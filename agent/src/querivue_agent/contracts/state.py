"""Strict serializable parent run-state projections."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .actions import Task
from .budgets import BudgetSnapshot
from .common import (
    Hash64, NonblankString, OwnerFence, PositiveCount, SafeCount, StrictRecord,
    TimestampText,
)
from .evidence import TabularEvidence
from .inputs import RunInput, SupervisorInput
from .responses import ActionOutcome
from .values import CanonicalUUID, UnicodeString


class ToolCallRecord(StrictRecord):
    call_id: NonblankString
    name: Literal[
        "inspect_table", "preview_rows", "inspect_evidence", "execute_query", "execute_python",
    ]
    arguments_json: UnicodeString
    provider_signature: UnicodeString | None


class ModelMessage(StrictRecord):
    role: Literal["system", "user", "assistant", "tool"]
    content: UnicodeString | None
    tool_calls: list[ToolCallRecord]
    tool_call_id: NonblankString | None

    @field_validator("tool_calls")
    @classmethod
    def unique_call_ids(cls, value: list[ToolCallRecord]) -> list[ToolCallRecord]:
        ids = [item.call_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("tool call IDs must be unique within a message")
        return value

    @model_validator(mode="after")
    def validate_message(self) -> "ModelMessage":
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages may contain tool calls")
        if self.role == "tool":
            if self.tool_call_id is None:
                raise ValueError("tool replies require tool_call_id")
        elif self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool replies")
        if self.content is None or self.content == "":
            if self.role != "assistant" or not self.tool_calls:
                raise ValueError("empty content is allowed only for assistant tool calls")
        return self


class ReviewReservationRef(StrictRecord):
    record_ref: CanonicalUUID
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    review_pass: int = Field(strict=True, ge=1, le=2)


class RunExecutionStatus(StrictRecord):
    phase: Literal[
        "queued", "planning", "analysis", "answer", "review", "clarification", "waiting",
        "finalization", "completed", "partial", "failed", "blocked", "invalidated",
        "cancelled", "expired",
    ]
    fence: OwnerFence
    budget: BudgetSnapshot
    deadline: TimestampText
    run_revision: SafeCount
    queue_revision: SafeCount
    expected_attempts: dict[CanonicalUUID, PositiveCount]
    active_draft_ref: CanonicalUUID | None
    active_review_ref: CanonicalUUID | None
    active_question_ref: CanonicalUUID | None
    analysis_started: bool
    review_reservations: list[ReviewReservationRef] = Field(max_length=2)

    @model_validator(mode="after")
    def validate_execution(self) -> "RunExecutionStatus":
        if self.fence.scope != self.budget.scope:
            raise ValueError("fence and budget scopes must match")
        passes = [item.review_pass for item in self.review_reservations]
        review_ids = [item.review_id for item in self.review_reservations]
        record_refs = [item.record_ref for item in self.review_reservations]
        if len(passes) != len(set(passes)):
            raise ValueError("review reservation passes must be unique")
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("review reservation IDs must be unique")
        if len(record_refs) != len(set(record_refs)):
            raise ValueError("review reservation record refs must be unique")
        return self


class RunState(StrictRecord):
    input: RunInput
    context: SupervisorInput
    evidence: dict[CanonicalUUID, TabularEvidence]
    messages: list[ModelMessage]
    pending_tasks: list[Task]
    current_task: Task | None
    outcomes: dict[CanonicalUUID, ActionOutcome]
    execution_status: RunExecutionStatus
    output: CanonicalUUID | None

    @model_validator(mode="after")
    def validate_state(self) -> "RunState":
        scope = self.context.scope
        if (
            scope.run_id != self.input.run_id
            or scope.project_id != self.input.project_id
            or scope.chat_id != self.input.chat_id
            or scope.eligible_dataset_ids != self.input.eligible_dataset_ids
        ):
            raise ValueError("input and context scopes must agree")
        if self.execution_status.fence.scope != scope or self.execution_status.budget.scope != scope:
            raise ValueError("execution scope must match input and context")
        if self.context.conversation.original_message.text != self.input.question:
            raise ValueError("run question must equal the original conversation question")
        if any(key != item.evidence_id for key, item in self.evidence.items()):
            raise ValueError("evidence map keys must equal inner evidence IDs")
        if any(key != item.action_id for key, item in self.outcomes.items()):
            raise ValueError("outcome map keys must equal inner action IDs")
        tasks = self.pending_tasks + ([self.current_task] if self.current_task is not None else [])
        task_ids = [item.task_id for item in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("pending and current task IDs must be unique")
        attempts = self.execution_status.expected_attempts
        if any(attempts.get(item.action_id) != item.attempt for item in self.outcomes.values()):
            raise ValueError("outcome attempts must match expected action attempts")
        return self


class GraphProjection(StrictRecord):
    schema_version: NonblankString
    graph_version: NonblankString
    run_id: CanonicalUUID
    thread_id: CanonicalUUID
    run_revision: SafeCount
    state: RunState
    serialized_at: TimestampText
    configuration_hash: Hash64
    namespace: NonblankString

    @model_validator(mode="after")
    def validate_projection(self) -> "GraphProjection":
        if self.thread_id != self.run_id or self.run_id != self.state.input.run_id:
            raise ValueError("thread, projection run, and state run IDs must match")
        if self.run_revision != self.state.execution_status.run_revision:
            raise ValueError("projection revision must match state execution revision")
        return self


class RunHandle(StrictRecord):
    run_id: CanonicalUUID
    status: Literal[
        "queued", "running", "waiting", "completed", "partial", "failed", "blocked",
        "invalidated", "cancelled", "expired",
    ]
    run_revision: SafeCount
    result_ref: CanonicalUUID | None
    reason: NonblankString | None

    @model_validator(mode="after")
    def validate_result(self) -> "RunHandle":
        if self.status in ("completed", "partial"):
            if self.result_ref is None:
                raise ValueError("completed and partial runs require result_ref")
        elif self.status in ("queued", "running", "waiting") and self.result_ref is not None:
            raise ValueError("queued, running, and waiting runs cannot have result_ref")
        return self

