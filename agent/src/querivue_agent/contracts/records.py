"""Strict durable runtime records; validation does not grant runtime authority."""

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BeforeValidator, Field, ValidationInfo, field_validator, model_validator

from .actions import DirectAnswer, Task
from .artifacts import ArtifactRef, SourceDependency
from .budgets import BudgetSnapshot
from .catalog import ImportSettings, ImportSettingsProposal
from .common import (
    Hash64,
    MoneyText,
    NonblankString,
    OwnerFence,
    PositiveCount,
    Role,
    SafeCount,
    Scope,
    StrictRecord,
    TimestampText,
)
from .content import BlockID, Draft
from .entry import EntryAccept, EntryInput as IntakeEntryInput, EntryOutcome
from .evidence import ChartArtifact, TabularEvidence
from .inputs import EntryInput, ReviewRequest, UserMessage
from .manifests import InferenceSettings, ProviderIdentity, ResourceProfile, SchemaDescriptor, ToolDeclaration
from .responses import ClarificationQuestionReady, ReviewedAssessment, ToolError
from .state import ModelMessage
from .tools import ExecutePythonRequest, ExecuteQueryRequest
from .values import CanonicalUUID, RuntimeUUID, UnicodeString


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _strict_true(value: object) -> object:
    if value is not True or type(value) is not bool:
        raise ValueError("expected the boolean true")
    return value


def _unique_strings(values: list[str], subject: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{subject} must be unique")


def _unique_dependencies(value: list[SourceDependency]) -> list[SourceDependency]:
    identities = [(item.dataset_id, item.snapshot_id) for item in value]
    if len(identities) != len(set(identities)):
        raise ValueError("source dependencies must be unique")
    return value


class ModelRequest(StrictRecord):
    request_id: RuntimeUUID
    invocation_id: CanonicalUUID
    scope: Scope
    role: Role
    action_id: CanonicalUUID | None
    intake_id: CanonicalUUID | None
    attempt: PositiveCount
    invocation_key: NonblankString
    packet_id: CanonicalUUID
    packet_hash: Hash64
    configuration_hash: Hash64
    provider: ProviderIdentity
    inference: InferenceSettings
    messages: list[ModelMessage] = Field(min_length=1)
    tools: list[ToolDeclaration]
    terminal_schema: SchemaDescriptor
    application_request: ArtifactRef
    max_input_tokens: PositiveCount
    created_at: TimestampText

    @model_validator(mode="after")
    def validate_request(self) -> "ModelRequest":
        names = [tool.name for tool in self.tools]
        _unique_strings(names, "tool names")
        required = {
            "sql": {"inspect_table", "preview_rows", "inspect_evidence", "execute_query"},
            "python": {"inspect_evidence", "execute_python"},
        }.get(self.role, set())
        if set(names) != required:
            raise ValueError("tool declarations must exactly match the request role")
        if self.max_input_tokens + self.inference.max_generated_tokens > self.provider.max_context_tokens:
            raise ValueError("requested tokens exceed provider context")
        if self.role == "entry":
            if self.intake_id is None:
                raise ValueError("entry request requires intake_id")
            if self.scope.run_id is not None:
                raise ValueError("entry request cannot carry run scope")
        elif self.scope.run_id is None:
            raise ValueError("non-entry request requires run scope")
        if self.application_request.media_type != "application/json":
            raise ValueError("application request artifact must use application/json")
        return self


class ModelUsage(StrictRecord):
    input_tokens: SafeCount | None
    output_tokens: SafeCount | None
    reasoning_tokens: SafeCount | None
    cached_input_tokens: SafeCount | None
    cost_usd: MoneyText | None
    raw_usage_ref: ArtifactRef | None

    @model_validator(mode="after")
    def validate_subtotals(self) -> "ModelUsage":
        if (
            self.reasoning_tokens is not None
            and self.output_tokens is not None
            and self.reasoning_tokens > self.output_tokens
        ):
            raise ValueError("reasoning_tokens cannot exceed known output_tokens")
        if (
            self.cached_input_tokens is not None
            and self.input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached_input_tokens cannot exceed known input_tokens")
        return self


class ModelCompletion(StrictRecord):
    completion_id: RuntimeUUID
    request_id: CanonicalUUID
    invocation_id: CanonicalUUID
    request_hash: Hash64
    status: Literal["completed", "incomplete", "unknown", "failed"]
    response_artifact: ArtifactRef | None
    provider_request_id: NonblankString | None
    observed_model_revision: NonblankString | None
    stop_reason: NonblankString | None
    usage: ModelUsage
    error_ref: CanonicalUUID | None
    recorded_at: TimestampText

    @model_validator(mode="after")
    def validate_status(self) -> "ModelCompletion":
        if self.status == "completed":
            if self.response_artifact is None or self.error_ref is not None:
                raise ValueError("completed response requires a raw response artifact and no error")
        elif self.status == "failed" and self.error_ref is None:
            raise ValueError("failed response requires error_ref")
        return self


class ModelReservation(StrictRecord):
    reservation_id: RuntimeUUID
    scope: Scope
    request_id: CanonicalUUID
    invocation_id: CanonicalUUID
    role: Role
    max_input_tokens: PositiveCount
    max_output_tokens: PositiveCount
    cost_usd: MoneyText
    admitted_at: TimestampText
    expires_at: TimestampText

    @model_validator(mode="after")
    def validate_expiry(self) -> "ModelReservation":
        if _timestamp(self.expires_at) <= _timestamp(self.admitted_at):
            raise ValueError("reservation expiry must follow admission")
        return self


class NewRunTarget(StrictRecord):
    kind: Literal["new_run"]
    run_id: RuntimeUUID


class ResumeRunTarget(StrictRecord):
    kind: Literal["resume_run"]
    run_id: CanonicalUUID
    question_id: CanonicalUUID
    reply_ref: CanonicalUUID


class IngestTarget(StrictRecord):
    kind: Literal["ingest"]
    dataset_id: RuntimeUUID
    upload: ArtifactRef


AdmissionTarget: TypeAlias = Annotated[
    NewRunTarget | ResumeRunTarget | IngestTarget,
    Field(discriminator="kind"),
]


class IntakeReceipt(StrictRecord):
    intake_id: RuntimeUUID
    submission_key: NonblankString
    input: IntakeEntryInput
    original_hash: Hash64
    fence: OwnerFence
    entry_question_id: CanonicalUUID | None
    outcome: EntryOutcome | None
    created_at: TimestampText
    expires_at: TimestampText
    status: Literal["pending", "waiting", "admitted", "rejected", "unavailable", "expired", "cancelled"]
    invocation_ids: list[CanonicalUUID]
    charge_ref: CanonicalUUID | None

    @field_validator("invocation_ids")
    @classmethod
    def unique_invocations(cls, value: list[str]) -> list[str]:
        _unique_strings(value, "invocation IDs")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> "IntakeReceipt":
        if self.input.submission_hash != self.original_hash:
            raise ValueError("input submission hash must equal original_hash")
        if (
            self.fence.subject_kind != "intake"
            or self.fence.subject_id != self.intake_id
            or self.fence.scope != self.input.scope
        ):
            raise ValueError("intake fence must bind the intake ID and input scope")
        if self.status == "waiting" and self.entry_question_id is None:
            raise ValueError("waiting receipt requires entry_question_id")
        if _timestamp(self.expires_at) <= _timestamp(self.created_at):
            raise ValueError("intake expiry must follow creation")
        return self


class IntakeAdmission(StrictRecord):
    admission_id: RuntimeUUID
    intake_id: CanonicalUUID
    submission_hash: Hash64
    scope: Scope
    assessment: EntryAccept
    context_hash: Hash64
    configuration_hash: Hash64
    policy_version: NonblankString
    target: AdmissionTarget
    fence: OwnerFence
    accepted_at: TimestampText

    @model_validator(mode="after")
    def validate_admission(self) -> "IntakeAdmission":
        if (
            self.fence.subject_kind != "intake"
            or self.fence.subject_id != self.intake_id
            or self.fence.scope != self.scope
        ):
            raise ValueError("admission fence must bind the intake ID and scope")
        if isinstance(self.target, ResumeRunTarget) and self.scope.run_id != self.target.run_id:
            raise ValueError("resume target run must equal scope.run_id")
        return self


class AdmissionReceipt(StrictRecord):
    receipt_id: RuntimeUUID
    admission_id: CanonicalUUID
    intake_id: CanonicalUUID
    run_id: CanonicalUUID
    scope: Scope
    cutoff_sequence: SafeCount
    budget: BudgetSnapshot
    configuration_hash: Hash64
    accepted_at: TimestampText

    @model_validator(mode="after")
    def validate_scope(self) -> "AdmissionReceipt":
        if self.scope.run_id != self.run_id or self.budget.scope != self.scope:
            raise ValueError("admission receipt run, scope, and budget must agree")
        return self


class QueueReceipt(StrictRecord):
    receipt_id: RuntimeUUID
    run_id: CanonicalUUID
    invocation_id: CanonicalUUID
    proposal_hash: Hash64
    decision_type: Literal["propose_queue", "stop"]
    previous_queue_revision: SafeCount
    queue_revision: SafeCount
    run_revision: PositiveCount
    task_mapping: dict[BlockID, CanonicalUUID]
    action_mapping: dict[BlockID, CanonicalUUID]
    tasks: list[Task] = Field(max_length=4)
    withdrawn_task_ids: list[CanonicalUUID]

    @field_validator("withdrawn_task_ids")
    @classmethod
    def unique_withdrawn_tasks(cls, value: list[str]) -> list[str]:
        _unique_strings(value, "withdrawn task IDs")
        return value

    @model_validator(mode="after")
    def validate_queue(self) -> "QueueReceipt":
        task_ids = [task.task_id for task in self.tasks]
        _unique_strings(task_ids, "task IDs")
        action_ids = [action.action_id for task in self.tasks for action in task.actions]
        _unique_strings(action_ids, "action IDs")
        _unique_strings(list(self.task_mapping.values()), "task mapping values")
        _unique_strings(list(self.action_mapping.values()), "action mapping values")
        if not set(self.task_mapping.values()) <= set(task_ids):
            raise ValueError("task mapping values must reference committed tasks")
        if not set(self.action_mapping.values()) <= set(action_ids):
            raise ValueError("action mapping values must reference committed actions")
        if set(self.withdrawn_task_ids) & set(task_ids):
            raise ValueError("withdrawn tasks cannot remain committed")
        if self.decision_type == "propose_queue":
            if not self.tasks or self.queue_revision != self.previous_queue_revision + 1:
                raise ValueError("propose_queue requires tasks and one queue revision increment")
        elif (
            self.tasks
            or self.task_mapping
            or self.action_mapping
            or self.queue_revision not in (self.previous_queue_revision, self.previous_queue_revision + 1)
        ):
            raise ValueError("stop requires empty queue material and at most one revision increment")
        return self


class ReviewReservation(StrictRecord):
    reservation_id: RuntimeUUID
    scope: Scope
    request: ReviewRequest
    review_input_packet_hash: Hash64
    fence: OwnerFence
    budget_reservation_id: CanonicalUUID
    reserved_at: TimestampText
    deadline: TimestampText
    max_physical_requests: PositiveCount
    max_input_tokens: PositiveCount
    max_output_tokens: PositiveCount
    cost_usd: MoneyText

    @model_validator(mode="after")
    def validate_reservation(self) -> "ReviewReservation":
        if self.fence.scope != self.scope:
            raise ValueError("review reservation and fence scopes must match")
        if _timestamp(self.deadline) <= _timestamp(self.reserved_at):
            raise ValueError("review deadline must follow reservation")
        return self


class ClarificationQuestionRecord(StrictRecord):
    question_id: RuntimeUUID
    scope: Scope
    action_id: CanonicalUUID
    attempt: PositiveCount
    owner_generation: PositiveCount
    slot: Annotated[int, Field(strict=True, ge=1, le=2)]
    question: ClarificationQuestionReady
    content_hash: Hash64
    input_packet_id: CanonicalUUID
    input_packet_hash: Hash64
    source_dependencies: list[SourceDependency]
    committed_at: TimestampText
    expires_at: TimestampText
    run_deadline: TimestampText
    budget_reservation_id: CanonicalUUID

    _dependencies_unique = field_validator("source_dependencies")(_unique_dependencies)

    @model_validator(mode="after")
    def validate_window(self) -> "ClarificationQuestionRecord":
        committed = _timestamp(self.committed_at)
        expires = _timestamp(self.expires_at)
        deadline = _timestamp(self.run_deadline)
        if not committed < expires <= deadline:
            raise ValueError("question timestamps must satisfy committed < expires <= run deadline")
        return self


class EntryQuestionRecord(StrictRecord):
    entry_question_id: RuntimeUUID
    intake_id: CanonicalUUID
    scope: Scope
    input: EntryInput
    question: NonblankString
    content_hash: Hash64
    committed_at: TimestampText
    expires_at: TimestampText

    @model_validator(mode="after")
    def validate_question(self) -> "EntryQuestionRecord":
        if self.scope != self.input.scope:
            raise ValueError("entry question scope must equal input scope")
        if self.entry_question_id == self.intake_id:
            raise ValueError("entry question and intake IDs must be distinct")
        if _timestamp(self.expires_at) <= _timestamp(self.committed_at):
            raise ValueError("entry question expiry must follow commit")
        return self


class LinkedReply(StrictRecord):
    reply_id: RuntimeUUID
    run_id: CanonicalUUID
    question_id: CanonicalUUID
    entry_intake_id: CanonicalUUID
    submission_key: NonblankString
    message: UserMessage
    selected_option_ids: list[BlockID]
    question_content_hash: Hash64
    accepted_at: TimestampText
    entry_admission_ref: CanonicalUUID

    @field_validator("selected_option_ids")
    @classmethod
    def unique_options(cls, value: list[str]) -> list[str]:
        _unique_strings(value, "selected option IDs")
        return value


class ResumeReceipt(StrictRecord):
    resume_id: RuntimeUUID
    run_id: CanonicalUUID
    question_id: CanonicalUUID
    reply_id: CanonicalUUID
    entry_intake_id: CanonicalUUID
    run_revision: PositiveCount
    owner_generation: PositiveCount
    accepted_at: TimestampText
    original_deadline: TimestampText
    scope: Scope

    @model_validator(mode="after")
    def validate_resume(self) -> "ResumeReceipt":
        if self.scope.run_id != self.run_id:
            raise ValueError("resume scope must match run_id")
        if _timestamp(self.accepted_at) >= _timestamp(self.original_deadline):
            raise ValueError("resume must be accepted before the original deadline")
        return self


class _FinalCandidateBase(StrictRecord):
    candidate_id: RuntimeUUID
    scope: Scope
    content_hash: Hash64
    rendered_text: UnicodeString
    rendering_policy_version: NonblankString
    dependencies: list[SourceDependency]
    source_input_hash: Hash64
    valid_until: TimestampText
    originating_invocation_id: CanonicalUUID

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)


class ReviewedCandidate(_FinalCandidateBase):
    kind: Literal["reviewed"]
    draft_id: CanonicalUUID
    draft: Draft
    completeness: Literal["complete", "partial"]
    review: ReviewedAssessment
    approval_ref: CanonicalUUID

    @model_validator(mode="after")
    def validate_review(self) -> "ReviewedCandidate":
        if self.review.verdict != "approved":
            raise ValueError("reviewed candidate requires approved review")
        if self.draft_id != self.review.draft_id or self.approval_ref != self.review.review_id:
            raise ValueError("candidate draft and approval IDs must match review")
        if self.content_hash != self.review.draft_content_hash:
            raise ValueError("candidate content hash must match review")
        if self.source_input_hash != self.review.draft_input_packet_hash:
            raise ValueError("candidate input hash must match review")
        if self.rendering_policy_version != self.review.rendering_policy_version:
            raise ValueError("candidate rendering policy must match review")
        has_unmet = bool(self.draft.unmet_deliverables)
        if (self.completeness == "partial") != has_unmet:
            raise ValueError("partial requires unmet deliverables and complete forbids them")
        return self


class DirectCandidate(_FinalCandidateBase):
    kind: Literal["direct"]
    action: DirectAnswer
    completeness: Literal["complete"]
    review_status: Literal["not_required_direct"]


FinalCandidate: TypeAlias = Annotated[
    ReviewedCandidate | DirectCandidate,
    Field(discriminator="kind"),
]


class AnswerResult(StrictRecord):
    kind: Literal["answer"]
    result_id: RuntimeUUID
    scope: Scope
    route: Literal["reviewed", "direct"]
    candidate_id: CanonicalUUID
    content_hash: Hash64
    completeness: Literal["complete", "partial"]
    rendered_text: UnicodeString
    rendering_policy_version: NonblankString
    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]
    dependencies: list[SourceDependency]
    published_at: TimestampText
    review_status: Literal["approved", "not_required_direct"]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @field_validator("evidence_ids", "chart_artifact_ids")
    @classmethod
    def unique_references(cls, value: list[str], info: ValidationInfo) -> list[str]:
        _unique_strings(value, info.field_name)
        return value

    @model_validator(mode="after")
    def validate_route(self) -> "AnswerResult":
        if self.route == "direct":
            if self.completeness != "complete" or self.review_status != "not_required_direct":
                raise ValueError("direct results must be complete and not require review")
        elif self.review_status != "approved":
            raise ValueError("reviewed results require approved review status")
        if (self.evidence_ids or self.chart_artifact_ids) and not self.dependencies:
            raise ValueError("source-backed result references require dependencies")
        return self


class NoticeResult(StrictRecord):
    kind: Literal["notice"]
    result_id: RuntimeUUID
    scope: Scope
    status: Literal["blocked", "failed", "invalidated", "cancelled", "expired", "verification_stopped"]
    reason_code: NonblankString
    rendered_text: UnicodeString
    error_ref: CanonicalUUID | None
    created_at: TimestampText
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)


FinalResult: TypeAlias = Annotated[AnswerResult | NoticeResult, Field(discriminator="kind")]


class DeletionReceipt(StrictRecord):
    deletion_id: RuntimeUUID
    project_id: CanonicalUUID
    dataset_id: CanonicalUUID
    tombstone_revision: PositiveCount
    invalidated_run_ids: list[CanonicalUUID]
    removed_result_ids: list[CanonicalUUID]
    deferred_artifact_ids: list[CanonicalUUID]
    retirement_pending_incarnation_ids: list[CanonicalUUID]
    committed_at: TimestampText

    @field_validator(
        "invalidated_run_ids",
        "removed_result_ids",
        "deferred_artifact_ids",
        "retirement_pending_incarnation_ids",
    )
    @classmethod
    def unique_references(cls, value: list[str], info: ValidationInfo) -> list[str]:
        _unique_strings(value, info.field_name)
        return value


class SandboxTicket(StrictRecord):
    ticket_id: RuntimeUUID
    scope: Scope
    sandbox_id: NonblankString
    command_id: NonblankString | None
    incarnation_id: RuntimeUUID
    action_id: CanonicalUUID
    operation_id: CanonicalUUID | None
    attempt: PositiveCount
    generation: PositiveCount
    environment_manifest_id: CanonicalUUID
    state: Literal[
        "prepared", "running", "executed", "validated", "published", "retiring",
        "retired", "unreachable",
    ]
    created_at: TimestampText
    expires_at: TimestampText

    @model_validator(mode="after")
    def validate_expiry(self) -> "SandboxTicket":
        if _timestamp(self.expires_at) <= _timestamp(self.created_at):
            raise ValueError("sandbox ticket expiry must follow creation")
        return self


class RetirementProof(StrictRecord):
    retirement_id: RuntimeUUID
    sandbox_id: NonblankString
    incarnation_id: CanonicalUUID
    confirmed_at: TimestampText
    method: Literal["provider_termination", "process_tree_reaped"]
    process_tree_terminated: Annotated[Literal[True], BeforeValidator(_strict_true)]
    proof_ref: CanonicalUUID
    environment_manifest_id: CanonicalUUID


PreparationSettings: TypeAlias = ImportSettings | ImportSettingsProposal


class PreparationAttempt(StrictRecord):
    dataset_id: CanonicalUUID
    attempt_id: RuntimeUUID
    attempt_number: PositiveCount
    settings: PreparationSettings
    settings_hash: Hash64
    upload: ArtifactRef
    upload_hash: Hash64
    owner_generation: PositiveCount
    phase: Literal[
        "staged", "inspecting", "awaiting_confirmation", "preparing", "validated",
        "transferred", "ready", "failed", "invalidated", "deleted",
    ]
    environment_manifest_id: CanonicalUUID | None
    incarnation_id: CanonicalUUID | None
    retirement_state: Literal["not_started", "active", "retirement_pending", "retired"]
    limits: ResourceProfile | None
    deadline: TimestampText
    diagnostic_ref: CanonicalUUID | None
    candidate_ref: CanonicalUUID | None
    publication_ref: CanonicalUUID | None

    @model_validator(mode="after")
    def validate_attempt(self) -> "PreparationAttempt":
        if self.upload_hash != self.upload.sha256:
            raise ValueError("upload hash must match artifact")
        if self.phase in ("preparing", "validated", "transferred", "ready"):
            if (
                not isinstance(self.settings, ImportSettings)
                or self.environment_manifest_id is None
                or self.limits is None
            ):
                raise ValueError("active preparation phases require confirmed settings, environment, and limits")
        if self.phase in ("validated", "transferred", "ready") and self.candidate_ref is None:
            raise ValueError("validated and later phases require candidate_ref")
        if self.phase == "ready" and self.publication_ref is None:
            raise ValueError("ready phase requires publication_ref")
        return self


class IngestionOperation(StrictRecord):
    dataset_id: CanonicalUUID
    upload: ArtifactRef
    settings: PreparationSettings


OperationPayload: TypeAlias = ExecuteQueryRequest | ExecutePythonRequest | IngestionOperation


class OperationRequest(StrictRecord):
    operation_id: RuntimeUUID
    scope: Scope
    task_id: CanonicalUUID | None
    action_id: CanonicalUUID | None
    attempt: PositiveCount
    execution_generation: PositiveCount
    invocation_key: NonblankString
    request_hash: Hash64
    kind: Literal["sql_query", "python_code", "ingestion_inspect", "ingestion_prepare"]
    request: OperationPayload
    input_artifacts: list[ArtifactRef]
    deadline: TimestampText
    environment_manifest_id: CanonicalUUID

    @model_validator(mode="after")
    def validate_operation(self) -> "OperationRequest":
        expected = {
            "sql_query": ExecuteQueryRequest,
            "python_code": ExecutePythonRequest,
            "ingestion_inspect": IngestionOperation,
            "ingestion_prepare": IngestionOperation,
        }[self.kind]
        if not isinstance(self.request, expected):
            raise ValueError("operation kind must match request payload")
        if self.kind in ("sql_query", "python_code"):
            if self.scope.run_id is None or self.task_id is None or self.action_id is None:
                raise ValueError("analysis operation requires run, task, and action")
        elif self.task_id is not None or self.action_id is not None:
            raise ValueError("ingestion operations cannot carry task or action IDs")
        if (
            self.kind == "ingestion_prepare"
            and isinstance(self.request, IngestionOperation)
            and not isinstance(self.request.settings, ImportSettings)
        ):
            raise ValueError("ingestion_prepare requires confirmed settings")
        return self


class OperationDiagnostics(StrictRecord):
    stdout: UnicodeString
    stderr: UnicodeString
    stdout_truncated: bool
    stderr_truncated: bool
    source_dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("source_dependencies")(_unique_dependencies)

    @field_validator("stdout", "stderr")
    @classmethod
    def bounded_output(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 16384:
            raise ValueError("captured output may contain at most 16384 UTF-8 bytes")
        return value


class _OperationOutcomeBase(StrictRecord):
    operation_id: CanonicalUUID
    attempt: PositiveCount
    execution_generation: PositiveCount
    request_hash: Hash64
    evidence: list[TabularEvidence]
    charts: list[ChartArtifact]
    diagnostics: OperationDiagnostics
    completed_at: TimestampText

    @model_validator(mode="after")
    def validate_outputs(self) -> "_OperationOutcomeBase":
        _unique_strings([item.evidence_id for item in self.evidence], "published evidence IDs")
        _unique_strings([item.chart_artifact_id for item in self.charts], "published chart IDs")
        return self


class OperationSucceeded(_OperationOutcomeBase):
    status: Literal["succeeded"]


class OperationFailed(_OperationOutcomeBase):
    status: Literal["failed"]
    error: ToolError


class OperationBlocked(_OperationOutcomeBase):
    status: Literal["blocked"]
    error: ToolError


OperationOutcome: TypeAlias = Annotated[
    OperationSucceeded | OperationFailed | OperationBlocked,
    Field(discriminator="status"),
]
