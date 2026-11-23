"""Resolved, immutable role-input packet contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, ValidationInfo, field_validator, model_validator

from .actions import AnswerAction, ClarificationAction, PythonAction, SQLAction, Task
from .artifacts import SourceDependency
from .budgets import BudgetSnapshot
from .catalog import SourceFormat, TableCatalog
from .common import (
    Hash64, NonblankString, OwnerFence, PositiveCount, Role, SafeCount, Scope,
    StrictRecord, TimestampText,
)
from .content import Draft
from .control import BasisReference, InterpretationUpdate, PartialAuthorization, UserMessageBasis
from .evidence import ChartArtifact, ProfileProducer, TabularEvidence
from .responses import (
    ActionOutcome, ClarificationQuestionReady, ReviewedAssessment, RoleOutcome,
)
from .values import CanonicalUUID, RuntimeUUID, UnicodeString


def _unique(values: list[str], subject: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{subject} must be unique")


def _unique_dependencies(value: list[SourceDependency]) -> list[SourceDependency]:
    pairs = [(item.dataset_id, item.snapshot_id) for item in value]
    if len(pairs) != len(set(pairs)):
        raise ValueError("dependencies must be unique")
    return value


def _dependency_pairs(value: list[SourceDependency]) -> set[tuple[str, str]]:
    return {(item.dataset_id, item.snapshot_id) for item in value}


class UserMessage(StrictRecord):
    message_id: CanonicalUUID
    chat_id: CanonicalUUID
    sequence: SafeCount
    text: UnicodeString
    content_hash: Hash64


class ContextRecord(StrictRecord):
    context_ref: CanonicalUUID
    kind: Literal[
        "metric_definition", "filter", "date_window", "timezone", "grain", "unit",
        "source_selection", "referent", "request_change", "assumption", "limitation", "help",
    ]
    text: UnicodeString
    basis_refs: list[BasisReference]
    dependencies: list[SourceDependency]
    scope: Literal["run", "thread", "chat_default"]
    status: Literal["user_stated", "runtime_reference", "tentative", "unresolved"]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @model_validator(mode="after")
    def validate_status(self) -> "ContextRecord":
        if self.status == "user_stated" and not any(
            isinstance(reference, UserMessageBasis) for reference in self.basis_refs
        ):
            raise ValueError("user_stated context requires a user-message basis")
        if self.kind == "help" and self.status != "runtime_reference":
            raise ValueError("help context must be a runtime reference")
        return self


class InterpretationRecord(StrictRecord):
    record_id: CanonicalUUID
    chat_id: CanonicalUUID
    revision: PositiveCount
    update: InterpretationUpdate
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)


class ObligationRecord(StrictRecord):
    obligation_ref: CanonicalUUID
    revision: PositiveCount
    description: NonblankString
    basis: UserMessageBasis
    state: Literal["operative", "withdrawn"]
    withdrawal_basis: UserMessageBasis | None
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @model_validator(mode="after")
    def validate_withdrawal(self) -> "ObligationRecord":
        if (self.state == "withdrawn") != (self.withdrawal_basis is not None):
            raise ValueError("withdrawn state requires, and only withdrawn state allows, withdrawal_basis")
        return self


class UnmetFact(StrictRecord):
    gap_ref: CanonicalUUID
    obligation_refs: list[CanonicalUUID]
    status: Literal["missing", "failed", "unresolved"]
    description: NonblankString
    error_ref: CanonicalUUID | None
    retained_evidence_ids: list[CanonicalUUID]

    @field_validator("obligation_refs", "retained_evidence_ids")
    @classmethod
    def unique_references(cls, value: list[str], info: ValidationInfo) -> list[str]:
        _unique(value, info.field_name)
        return value


class ThreadCandidate(StrictRecord):
    thread_id: CanonicalUUID
    chat_id: CanonicalUUID
    sequence: SafeCount
    result_ref: CanonicalUUID | None
    published_response: UnicodeString | None
    description: NonblankString
    status: Literal["tentative", "unavailable"]
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @model_validator(mode="after")
    def validate_publication(self) -> "ThreadCandidate":
        if self.published_response is not None and self.result_ref is None:
            raise ValueError("published_response requires result_ref")
        return self


class ContextConflict(StrictRecord):
    conflict_id: CanonicalUUID
    context_refs: list[CanonicalUUID] = Field(min_length=1)
    description: NonblankString

    @field_validator("context_refs")
    @classmethod
    def unique_contexts(cls, value: list[str]) -> list[str]:
        _unique(value, "context_refs")
        return value


class LinkedReplyContext(StrictRecord):
    question_id: CanonicalUUID
    question: ClarificationQuestionReady
    reply: UserMessage
    entry_intake_id: CanonicalUUID
    accepted_reply_ref: CanonicalUUID
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)


class ConversationSnapshot(StrictRecord):
    snapshot_id: CanonicalUUID
    chat_id: CanonicalUUID
    cutoff_sequence: SafeCount
    original_message: UserMessage
    linked_replies: list[LinkedReplyContext]
    context_records: list[ContextRecord]
    interpretation_records: list[InterpretationRecord]
    thread_index: list[ThreadCandidate]
    conflicts: list[ContextConflict]

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ConversationSnapshot":
        for values, subject in (
            ([item.question_id for item in self.linked_replies], "linked question IDs"),
            ([item.reply.message_id for item in self.linked_replies], "linked reply message IDs"),
            ([item.accepted_reply_ref for item in self.linked_replies], "accepted reply refs"),
            ([item.context_ref for item in self.context_records], "context refs"),
            ([item.record_id for item in self.interpretation_records], "interpretation record IDs"),
            ([item.thread_id for item in self.thread_index], "thread IDs"),
            ([item.conflict_id for item in self.conflicts], "conflict IDs"),
        ):
            _unique(values, subject)
        if self.original_message.chat_id != self.chat_id:
            raise ValueError("original message chat must match snapshot chat")
        if self.original_message.sequence > self.cutoff_sequence:
            raise ValueError("original message must be within the snapshot cutoff")
        if any(item.reply.chat_id != self.chat_id for item in self.linked_replies):
            raise ValueError("linked replies must belong to the snapshot chat")
        if any(item.chat_id != self.chat_id for item in self.interpretation_records):
            raise ValueError("interpretation records must belong to the snapshot chat")
        if any(
            item.chat_id != self.chat_id or item.sequence > self.cutoff_sequence
            for item in self.thread_index
        ):
            raise ValueError("thread candidates must belong to the chat and cutoff")
        context_ids = {item.context_ref for item in self.context_records}
        if any(not set(item.context_refs) <= context_ids for item in self.conflicts):
            raise ValueError("conflicts must reference supplied context records")
        message_ids = {self.original_message.message_id} | {
            item.reply.message_id for item in self.linked_replies
        }
        bases: list[UserMessageBasis] = []
        for item in self.context_records:
            bases.extend(ref for ref in item.basis_refs if isinstance(ref, UserMessageBasis))
        for item in self.interpretation_records:
            bases.extend(ref for ref in item.update.basis_refs if isinstance(ref, UserMessageBasis))
        if any(item.message_id not in message_ids for item in bases):
            raise ValueError("user-message bases must reference supplied messages")
        return self


class RecordSelection(StrictRecord):
    record_id: CanonicalUUID
    content_hash: Hash64
    revision: SafeCount
    category: Literal[
        "message", "context", "interpretation", "obligation", "evidence", "chart",
        "catalog", "outcome", "gap", "draft", "review",
    ]
    required: bool


class CoverageNotice(StrictRecord):
    category: Literal["history", "context", "evidence", "chart", "catalog", "outcome", "obligation"]
    reason: Literal["omitted", "unavailable", "known_absent"]
    record_refs: list[CanonicalUUID]
    explanation: NonblankString

    @field_validator("record_refs")
    @classmethod
    def unique_records(cls, value: list[str]) -> list[str]:
        _unique(value, "record_refs")
        return value


class PacketMetadata(StrictRecord):
    packet_id: RuntimeUUID
    content_hash: Hash64
    policy_version: NonblankString
    configuration_hash: Hash64
    base_snapshot_id: CanonicalUUID
    selected_records: list[RecordSelection]
    dependencies: list[SourceDependency]
    coverage: list[CoverageNotice]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @field_validator("selected_records")
    @classmethod
    def unique_selections(cls, value: list[RecordSelection]) -> list[RecordSelection]:
        identities = [(item.category, item.record_id) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("selected record identities must be unique")
        return value


class RuntimeControls(StrictRecord):
    fence: OwnerFence
    budget: BudgetSnapshot
    deadline: TimestampText
    environment_manifest_id: CanonicalUUID | None
    environment_version: NonblankString | None
    policy_version: NonblankString
    phase: Literal[
        "queued", "planning", "analysis", "answer", "review", "clarification",
        "waiting", "finalization", "terminal",
    ]
    active_operation_id: CanonicalUUID | None

    @model_validator(mode="after")
    def validate_controls(self) -> "RuntimeControls":
        if self.fence.scope != self.budget.scope:
            raise ValueError("fence and budget scopes must match")
        if (self.environment_manifest_id is None) != (self.environment_version is None):
            raise ValueError("environment manifest and version must be supplied together")
        return self


class RunInput(StrictRecord):
    run_id: CanonicalUUID
    project_id: CanonicalUUID
    chat_id: CanonicalUUID
    question: UnicodeString
    eligible_dataset_ids: list[CanonicalUUID]

    @field_validator("eligible_dataset_ids")
    @classmethod
    def unique_datasets(cls, value: list[str]) -> list[str]:
        _unique(value, "eligible_dataset_ids")
        return value


class DatasetChoice(StrictRecord):
    dataset_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    label: UnicodeString
    source_format: SourceFormat


class RevisionContext(StrictRecord):
    predecessor_draft_id: CanonicalUUID
    previous_draft: Draft
    review: ReviewedAssessment
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)

    @model_validator(mode="after")
    def validate_revision(self) -> "RevisionContext":
        if self.predecessor_draft_id != self.review.draft_id:
            raise ValueError("predecessor draft must match the reviewed draft")
        if self.review.verdict != "rejected" or self.review.review_pass != 1:
            raise ValueError("revision requires a rejected pass-one review")
        return self


class ReviewRequest(StrictRecord):
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    draft_content_hash: Hash64
    draft_input_packet_hash: Hash64
    rendering_policy_version: NonblankString
    review_pass: Annotated[int, Field(strict=True, ge=1, le=2)]


class _AnalyticalInput(StrictRecord):
    role: Role
    packet: PacketMetadata
    scope: Scope
    conversation: ConversationSnapshot
    controls: RuntimeControls

    def _material_ids(self) -> dict[str, set[str]]:
        return {
            "message": {self.conversation.original_message.message_id} | {
                item.reply.message_id for item in self.conversation.linked_replies
            },
            "context": {item.context_ref for item in self.conversation.context_records},
            "interpretation": {item.record_id for item in self.conversation.interpretation_records},
        }

    def _dependencies(self) -> list[SourceDependency]:
        dependencies = [
            dependency
            for item in self.conversation.linked_replies
            for dependency in item.dependencies
        ]
        dependencies.extend(
            dependency for item in self.conversation.context_records for dependency in item.dependencies
        )
        dependencies.extend(
            dependency for item in self.conversation.interpretation_records for dependency in item.dependencies
        )
        dependencies.extend(
            dependency for item in self.conversation.thread_index for dependency in item.dependencies
        )
        return dependencies

    @model_validator(mode="after")
    def validate_common_packet(self) -> "_AnalyticalInput":
        if self.scope.run_id is None or self.scope.chat_id is None:
            raise ValueError("analytical packets require run and chat scope")
        if self.scope.chat_id != self.conversation.chat_id:
            raise ValueError("conversation chat must match packet scope")
        if self.packet.base_snapshot_id != self.conversation.snapshot_id:
            raise ValueError("packet base snapshot must match the conversation snapshot")
        if self.controls.fence.scope != self.scope or self.controls.budget.scope != self.scope:
            raise ValueError("control scopes must match packet scope")
        if self.packet.policy_version != self.controls.policy_version:
            raise ValueError("packet and controls policy versions must match")
        eligible = set(self.scope.eligible_dataset_ids)
        supplied_dependencies = self._dependencies()
        all_dependencies = list(self.packet.dependencies) + supplied_dependencies
        if any(item.dataset_id not in eligible for item in all_dependencies):
            raise ValueError("all dependencies must use an eligible dataset")
        if not _dependency_pairs(supplied_dependencies) <= _dependency_pairs(self.packet.dependencies):
            raise ValueError("packet dependencies must cover all supplied source-bearing dependencies")
        material = self._material_ids()
        for selection in self.packet.selected_records:
            if selection.required and selection.record_id not in material.get(selection.category, set()):
                raise ValueError("required selected records must have supplied typed material")
        message_ids = material["message"]
        for obligation in getattr(self, "obligations", []):
            bases = [obligation.basis]
            if obligation.withdrawal_basis is not None:
                bases.append(obligation.withdrawal_basis)
            if any(item.message_id not in message_ids for item in bases):
                raise ValueError("obligation bases must reference supplied messages")
        return self


class SQLInput(_AnalyticalInput):
    role: Literal["sql"]
    task_id: CanonicalUUID
    attempt: PositiveCount
    request: SQLAction
    tables: list[TableCatalog]
    evidence: list[TabularEvidence]
    table_profiles: list[TabularEvidence]

    def _material_ids(self) -> dict[str, set[str]]:
        result = super()._material_ids()
        result["catalog"] = {item.table_id for item in self.tables}
        result["evidence"] = {item.evidence_id for item in self.evidence + self.table_profiles}
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return super()._dependencies() + [
            dependency for item in self.evidence + self.table_profiles for dependency in item.dependencies
        ] + [SourceDependency(dataset_id=item.dataset_id, snapshot_id=item.snapshot_id) for item in self.tables]

    @model_validator(mode="after")
    def validate_sql(self) -> "SQLInput":
        _unique([item.table_id for item in self.tables], "table IDs")
        _unique([item.evidence_id for item in self.evidence + self.table_profiles], "evidence IDs")
        if set(item.table_id for item in self.tables) != set(self.request.table_ids):
            raise ValueError("tables must exactly match delegated table IDs")
        if set(item.evidence_id for item in self.evidence) != set(self.request.input_evidence_ids):
            raise ValueError("evidence must exactly match delegated evidence IDs")
        table_by_id = {item.table_id: item for item in self.tables}
        for profile in self.table_profiles:
            if not isinstance(profile.producer, ProfileProducer):
                raise ValueError("table profiles require ingestion_profile producers")
            table = table_by_id.get(profile.producer.table_id)
            if table is None or (table.dataset_id, table.snapshot_id) != (
                profile.producer.dataset_id, profile.producer.snapshot_id,
            ):
                raise ValueError("table profile must match a delegated table snapshot")
            if profile.evidence_id not in table.profile_evidence_ids:
                raise ValueError("table profile evidence must be declared by its table catalog")
        if self.controls.environment_manifest_id is None:
            raise ValueError("SQL packets require an environment")
        return self


class PythonInput(_AnalyticalInput):
    role: Literal["python"]
    task_id: CanonicalUUID
    attempt: PositiveCount
    request: PythonAction
    evidence: list[TabularEvidence]

    def _material_ids(self) -> dict[str, set[str]]:
        result = super()._material_ids()
        result["evidence"] = {item.evidence_id for item in self.evidence}
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return super()._dependencies() + [
            dependency for item in self.evidence for dependency in item.dependencies
        ]

    @model_validator(mode="after")
    def validate_python(self) -> "PythonInput":
        _unique([item.evidence_id for item in self.evidence], "evidence IDs")
        if set(item.evidence_id for item in self.evidence) != set(self.request.input_evidence_ids):
            raise ValueError("evidence must exactly match delegated evidence IDs")
        if self.controls.environment_manifest_id is None:
            raise ValueError("Python packets require an environment")
        return self


class AnswerInput(_AnalyticalInput):
    role: Literal["answer"]
    task_id: CanonicalUUID
    attempt: PositiveCount
    request: AnswerAction
    evidence: list[TabularEvidence]
    charts: list[ChartArtifact]
    obligations: list[ObligationRecord]
    unmet_facts: list[UnmetFact]
    partial_authorization: PartialAuthorization | None
    revision: RevisionContext | None

    def _material_ids(self) -> dict[str, set[str]]:
        result = super()._material_ids()
        result.update({
            "evidence": {item.evidence_id for item in self.evidence},
            "chart": {item.chart_artifact_id for item in self.charts},
            "obligation": {item.obligation_ref for item in self.obligations},
            "gap": {item.gap_ref for item in self.unmet_facts},
        })
        if self.revision is not None:
            result["draft"] = {self.revision.predecessor_draft_id}
            result["review"] = {self.revision.review.review_id}
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return super()._dependencies() + [
            dependency for item in self.evidence for dependency in item.dependencies
        ] + [dependency for item in self.charts for dependency in item.dependencies] + [
            dependency for item in self.obligations for dependency in item.dependencies
        ] + ([] if self.revision is None else list(self.revision.dependencies))

    @model_validator(mode="after")
    def validate_answer(self) -> "AnswerInput":
        for values, subject in (
            ([item.evidence_id for item in self.evidence], "evidence IDs"),
            ([item.chart_artifact_id for item in self.charts], "chart IDs"),
            ([item.obligation_ref for item in self.obligations], "obligation refs"),
            ([item.gap_ref for item in self.unmet_facts], "gap refs"),
        ):
            _unique(values, subject)
        if set(item.chart_artifact_id for item in self.charts) != set(self.request.chart_artifact_ids):
            raise ValueError("charts must exactly match selected chart IDs")
        expected_evidence = set(self.request.evidence_ids) | {
            evidence_id for chart in self.charts for evidence_id in chart.backing_evidence_ids
        }
        if set(item.evidence_id for item in self.evidence) != expected_evidence:
            raise ValueError("evidence must include request and chart-backing evidence exactly")
        if bool(self.unmet_facts) != (self.partial_authorization is not None):
            raise ValueError("unmet facts and partial authorization must be supplied together")
        if self.partial_authorization is not None:
            gaps = {item.gap_ref for item in self.unmet_facts}
            obligations = {ref for item in self.unmet_facts for ref in item.obligation_refs}
            supplied_obligations = {item.obligation_ref for item in self.obligations}
            if set(self.partial_authorization.gap_refs) != gaps:
                raise ValueError("partial authorization gap refs must match unmet facts")
            if not set(self.partial_authorization.unmet_obligation_refs) <= obligations:
                raise ValueError("partial authorization obligations must resolve through unmet facts")
            if not obligations <= supplied_obligations:
                raise ValueError("unmet facts must reference supplied obligations")
            supplied_support = {
                item.evidence_id for item in self.evidence
            } | {item.chart_artifact_id for item in self.charts}
            if not set(self.partial_authorization.supporting_refs) <= supplied_support:
                raise ValueError("partial authorization support must resolve to supplied material")
        if not {
            evidence_id for item in self.unmet_facts for evidence_id in item.retained_evidence_ids
        } <= {item.evidence_id for item in self.evidence}:
            raise ValueError("retained gap evidence must be supplied")
        return self


class ReviewInput(_AnalyticalInput):
    role: Literal["reviewer"]
    request: ReviewRequest
    draft: Draft
    rendered_text: UnicodeString
    draft_input: AnswerInput
    review_input_packet_hash: Hash64

    def _material_ids(self) -> dict[str, set[str]]:
        result = self.draft_input._material_ids()
        result["draft"] = {self.request.draft_id}
        result["review"] = {self.request.review_id}
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return list(self.draft_input.packet.dependencies) + self.draft_input._dependencies()

    @model_validator(mode="after")
    def validate_review(self) -> "ReviewInput":
        if self.scope != self.draft_input.scope or self.conversation != self.draft_input.conversation:
            raise ValueError("review scope and conversation must equal the frozen draft input")
        if self.request.draft_input_packet_hash != self.draft_input.packet.content_hash:
            raise ValueError("review request must bind the draft input packet hash")
        if self.review_input_packet_hash != self.packet.content_hash:
            raise ValueError("review input packet hash must equal this packet content hash")
        return self


class ClarificationInput(_AnalyticalInput):
    role: Literal["clarification"]
    task_id: CanonicalUUID
    attempt: PositiveCount
    request: ClarificationAction
    evidence: list[TabularEvidence]
    obligations: list[ObligationRecord]
    source_choices: list[DatasetChoice]

    def _material_ids(self) -> dict[str, set[str]]:
        result = super()._material_ids()
        result["evidence"] = {item.evidence_id for item in self.evidence}
        result["obligation"] = {item.obligation_ref for item in self.obligations}
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return super()._dependencies() + [
            dependency for item in self.evidence for dependency in item.dependencies
        ] + [dependency for item in self.obligations for dependency in item.dependencies] + [
            SourceDependency(dataset_id=item.dataset_id, snapshot_id=item.snapshot_id)
            for item in self.source_choices
        ]

    @model_validator(mode="after")
    def validate_clarification(self) -> "ClarificationInput":
        for values, subject in (
            ([item.evidence_id for item in self.evidence], "evidence IDs"),
            ([item.obligation_ref for item in self.obligations], "obligation refs"),
            ([item.dataset_id for item in self.source_choices], "source choice dataset IDs"),
        ):
            _unique(values, subject)
        if set(item.evidence_id for item in self.evidence) != set(self.request.input_evidence_ids):
            raise ValueError("evidence must exactly match delegated evidence IDs")
        contexts = {item.context_ref for item in self.conversation.context_records}
        if not set(self.request.context_refs) <= contexts:
            raise ValueError("clarification context refs must resolve to supplied records")
        return self


class SupervisorInput(_AnalyticalInput):
    role: Literal["supervisor"]
    pending_tasks: list[Task]
    current_task: Task | None
    outcomes: list[ActionOutcome]
    evidence: list[TabularEvidence]
    charts: list[ChartArtifact]
    catalog: list[TableCatalog]
    obligations: list[ObligationRecord]
    gaps: list[UnmetFact]
    source_choices: list[DatasetChoice]
    queue_revision: SafeCount
    analysis_started: bool

    def _material_ids(self) -> dict[str, set[str]]:
        result = super()._material_ids()
        result.update({
            "outcome": {item.result_ref for item in self.outcomes},
            "evidence": {item.evidence_id for item in self.evidence},
            "chart": {item.chart_artifact_id for item in self.charts},
            "catalog": {item.table_id for item in self.catalog},
            "obligation": {item.obligation_ref for item in self.obligations},
            "gap": {item.gap_ref for item in self.gaps},
        })
        return result

    def _dependencies(self) -> list[SourceDependency]:
        return super()._dependencies() + [
            dependency for item in self.evidence for dependency in item.dependencies
        ] + [dependency for item in self.charts for dependency in item.dependencies] + [
            SourceDependency(dataset_id=item.dataset_id, snapshot_id=item.snapshot_id)
            for item in self.catalog + self.source_choices
        ] + [dependency for item in self.obligations for dependency in item.dependencies]

    @model_validator(mode="after")
    def validate_supervisor(self) -> "SupervisorInput":
        tasks = self.pending_tasks + ([self.current_task] if self.current_task is not None else [])
        for values, subject in (
            ([item.task_id for item in tasks], "task IDs"),
            ([action.action_id for item in tasks for action in item.actions], "task action IDs"),
            ([item.action_id for item in self.outcomes], "outcome action IDs"),
            ([item.result_ref for item in self.outcomes], "outcome result refs"),
            ([item.evidence_id for item in self.evidence], "evidence IDs"),
        ):
            _unique(values, subject)
        supplied_obligations = {item.obligation_ref for item in self.obligations}
        if not {
            obligation for item in self.gaps for obligation in item.obligation_refs
        } <= supplied_obligations:
            raise ValueError("gaps must reference supplied obligations")
        if not {
            evidence_id for item in self.gaps for evidence_id in item.retained_evidence_ids
        } <= {item.evidence_id for item in self.evidence}:
            raise ValueError("retained gap evidence must be supplied")
        return self


class AnalyticalReplyLink(StrictRecord):
    kind: Literal["analytical_reply"]
    run_id: CanonicalUUID
    question_id: CanonicalUUID
    original_question: UnicodeString
    pending_question: ClarificationQuestionReady
    dependencies: list[SourceDependency]

    _dependencies_unique = field_validator("dependencies")(_unique_dependencies)


class EntryReplyLink(StrictRecord):
    kind: Literal["entry_reply"]
    parent_intake_id: CanonicalUUID
    entry_question_id: CanonicalUUID
    original_submission: UnicodeString
    entry_question: NonblankString
    analytical_link: AnalyticalReplyLink | None


EntryLink: TypeAlias = Annotated[AnalyticalReplyLink | EntryReplyLink, Field(discriminator="kind")]


class EntryInput(StrictRecord):
    role: Literal["entry"]
    packet: PacketMetadata
    scope: Scope
    input_kind: Literal["new_question", "analytical_reply", "entry_reply", "upload_instructions"]
    submission_text: NonblankString
    submission_hash: Hash64
    policy_version: NonblankString
    linked_context: EntryLink | None
    followup_context: list[ThreadCandidate]
    cutoff_sequence: SafeCount | None

    @model_validator(mode="after")
    def validate_entry(self) -> "EntryInput":
        expected_kind = self.linked_context.kind if self.linked_context is not None else None
        if self.input_kind in ("new_question", "upload_instructions"):
            if self.linked_context is not None:
                raise ValueError("new questions and upload instructions cannot carry linked context")
        elif expected_kind != self.input_kind:
            raise ValueError("linked context kind must match input kind")
        if isinstance(self.linked_context, AnalyticalReplyLink):
            if self.linked_context.run_id != self.scope.run_id:
                raise ValueError("analytical link run must match scope")
        elif isinstance(self.linked_context, EntryReplyLink) and self.linked_context.analytical_link is not None:
            if self.linked_context.analytical_link.run_id != self.scope.run_id:
                raise ValueError("nested analytical link run must match scope")
        if self.submission_hash != hashlib.sha256(self.submission_text.encode("utf-8")).hexdigest():
            raise ValueError("submission_hash must be the SHA-256 of exact UTF-8 submission text")
        if self.policy_version != self.packet.policy_version:
            raise ValueError("entry and packet policy versions must match")
        if self.scope.chat_id is None:
            if self.cutoff_sequence is not None or self.followup_context:
                raise ValueError("followup context and cutoff require a scoped chat")
        else:
            if self.cutoff_sequence is None:
                raise ValueError("scoped chat entry requires cutoff_sequence")
            if any(item.chat_id != self.scope.chat_id for item in self.followup_context):
                raise ValueError("followup context must belong to the scoped chat")
            if any(item.sequence > self.cutoff_sequence for item in self.followup_context):
                raise ValueError("followup context must be within the entry cutoff")
        eligible = set(self.scope.eligible_dataset_ids)
        supplied_dependencies = [
            dependency for item in self.followup_context for dependency in item.dependencies
        ]
        if isinstance(self.linked_context, AnalyticalReplyLink):
            supplied_dependencies.extend(self.linked_context.dependencies)
        elif isinstance(self.linked_context, EntryReplyLink):
            if self.linked_context.analytical_link is not None:
                supplied_dependencies.extend(self.linked_context.analytical_link.dependencies)
        dependencies = list(self.packet.dependencies) + supplied_dependencies
        if any(item.dataset_id not in eligible for item in dependencies):
            raise ValueError("all dependencies must use an eligible dataset")
        if not _dependency_pairs(supplied_dependencies) <= _dependency_pairs(self.packet.dependencies):
            raise ValueError("packet dependencies must cover supplied followup and linked-question lineage")
        available_outcomes = {
            item.result_ref for item in self.followup_context
            if item.result_ref is not None and item.published_response is not None
        }
        for selection in self.packet.selected_records:
            if selection.required and (
                selection.category != "outcome" or selection.record_id not in available_outcomes
            ):
                raise ValueError("required selected records must have supplied typed material")
        return self


RoleInput: TypeAlias = Annotated[
    EntryInput | SupervisorInput | SQLInput | PythonInput | AnswerInput | ReviewInput
    | ClarificationInput,
    Field(discriminator="role"),
]
RoleHandlers: TypeAlias = Mapping[Role, Callable[[RoleInput], RoleOutcome]]

