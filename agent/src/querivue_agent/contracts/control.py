"""Strict interpretation, obligation, and supervisor decision contracts."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator, model_validator

from .actions import (
    ExistingTaskReference, NewActionProposal, PendingTaskProposal, RetryActionReference,
    TaskProposal,
)
from .common import SafeCount, StrictRecord
from .content import BlockID, SupportTarget
from .values import CanonicalUUID, UnicodeString


def _utf8_text(limit: int, *, nonblank: bool = True):
    def validate(value: str) -> str:
        if nonblank and not value.strip():
            raise ValueError("expected a nonblank string")
        if len(value.encode("utf-8")) > limit:
            raise ValueError(f"expected at most {limit} UTF-8 bytes")
        return value
    return validate


def _nonempty(value: str) -> str:
    if not value:
        raise ValueError("expected a nonempty string")
    return value


Text2048 = Annotated[UnicodeString, Field(strict=True), AfterValidator(_utf8_text(2048))]
Quote2048 = Annotated[
    UnicodeString, Field(strict=True), AfterValidator(_nonempty),
    AfterValidator(_utf8_text(2048, nonblank=False)),
]


def _unique(values: list[str], name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return values


class UserMessageBasis(StrictRecord):
    kind: Literal["user_message"]
    message_id: CanonicalUUID
    start_byte: SafeCount
    end_byte: SafeCount
    quote: Quote2048

    @model_validator(mode="after")
    def validate_span(self) -> "UserMessageBasis":
        if self.end_byte <= self.start_byte:
            raise ValueError("end_byte must exceed start_byte")
        if len(self.quote.encode("utf-8")) != self.end_byte - self.start_byte:
            raise ValueError("quote byte length must equal the byte span")
        return self


BasisReference = Annotated[UserMessageBasis | SupportTarget, Field(discriminator="kind")]


class InterpretationUpdate(StrictRecord):
    key: BlockID
    kind: Literal[
        "metric_definition", "filter", "date_window", "timezone", "grain", "unit",
        "source_selection", "referent", "request_change",
    ]
    text: Text2048
    status: Literal["user_stated", "tentative", "unresolved"]
    scope: Literal["run", "thread", "chat_default"]
    basis_refs: list[BasisReference] = Field(max_length=32)
    supersedes_record_id: CanonicalUUID | None

    @model_validator(mode="after")
    def validate_user_basis(self) -> "InterpretationUpdate":
        if self.status == "user_stated" and not any(
            isinstance(reference, UserMessageBasis) for reference in self.basis_refs
        ):
            raise ValueError("user_stated interpretations require a user message basis")
        return self


class ObligationUpdate(StrictRecord):
    operation: Literal["create", "revise", "withdraw"]
    obligation_key: BlockID | None
    obligation_ref: CanonicalUUID | None
    description: Text2048
    basis: UserMessageBasis
    revision_basis: UserMessageBasis | None

    @model_validator(mode="after")
    def validate_operation(self) -> "ObligationUpdate":
        if self.operation == "create":
            if self.obligation_key is None or self.obligation_ref is not None or self.revision_basis is not None:
                raise ValueError("create requires a key and no reference or revision basis")
        elif self.obligation_ref is None or self.obligation_key is not None or self.revision_basis is None:
            raise ValueError("revise and withdraw require a reference and revision basis, and no key")
        return self


class ObligationCheckItem(StrictRecord):
    obligation_ref: CanonicalUUID
    status: Literal["supported", "missing", "unresolved", "explicitly_withdrawn_by_user"]
    support_refs: list[SupportTarget] = Field(max_length=32)
    outcome_refs: list[CanonicalUUID] = Field(max_length=32)
    gap_refs: list[CanonicalUUID] = Field(max_length=32)
    task_keys: list[BlockID] = Field(max_length=32)
    task_refs: list[CanonicalUUID] = Field(max_length=32)
    explanation: Text2048
    withdrawal_basis: UserMessageBasis | None

    @field_validator("outcome_refs", "gap_refs", "task_keys", "task_refs")
    @classmethod
    def unique_references(cls, value: list[str], info):
        return _unique(value, info.field_name)

    @model_validator(mode="after")
    def validate_status(self) -> "ObligationCheckItem":
        if self.status == "supported" and not (self.support_refs or self.outcome_refs):
            raise ValueError("supported obligations require support or outcome references")
        if self.status in ("missing", "unresolved") and not self.gap_refs:
            raise ValueError("missing and unresolved obligations require gap_refs")
        if self.status == "explicitly_withdrawn_by_user":
            if self.withdrawal_basis is None:
                raise ValueError("withdrawn obligations require withdrawal_basis")
        elif self.withdrawal_basis is not None:
            raise ValueError("withdrawal_basis is only valid for withdrawn obligations")
        return self


class ObligationCheck(StrictRecord):
    items: list[ObligationCheckItem] = Field(max_length=32)

    @field_validator("items")
    @classmethod
    def unique_obligations(cls, value: list[ObligationCheckItem]) -> list[ObligationCheckItem]:
        references = [item.obligation_ref for item in value]
        if len(references) != len(set(references)):
            raise ValueError("obligation_ref values must be unique")
        return value


class PartialAuthorization(StrictRecord):
    partial_answer_allowed: Literal[True]
    reason: Text2048
    unmet_obligation_refs: list[CanonicalUUID] = Field(max_length=32)
    gap_refs: list[CanonicalUUID] = Field(max_length=32)
    supporting_refs: list[CanonicalUUID] = Field(max_length=32)

    @field_validator("partial_answer_allowed", mode="before")
    @classmethod
    def require_literal_boolean_true(cls, value: object) -> object:
        if type(value) is not bool or value is not True:
            raise ValueError("partial_answer_allowed must be the boolean true")
        return value

    @field_validator("unmet_obligation_refs", "gap_refs", "supporting_refs")
    @classmethod
    def unique_references(cls, value: list[str], info):
        return _unique(value, info.field_name)

    @model_validator(mode="after")
    def require_unmet_or_gap(self) -> "PartialAuthorization":
        if not (self.unmet_obligation_refs or self.gap_refs):
            raise ValueError("partial authorization requires an unmet obligation or gap")
        return self


class _DecisionBase(StrictRecord):
    expected_queue_revision: SafeCount
    interpretation_updates: list[InterpretationUpdate] = Field(default_factory=list, max_length=8)
    obligation_updates: list[ObligationUpdate] = Field(default_factory=list, max_length=32)
    obligation_check: ObligationCheck | None = None
    partial_authorization: PartialAuthorization | None = None

    @model_validator(mode="after")
    def validate_update_uniqueness(self):
        _unique([update.key for update in self.interpretation_updates], "interpretation keys")
        _unique(
            [update.obligation_key for update in self.obligation_updates if update.operation == "create"],
            "created obligation keys",
        )
        _unique(
            [update.obligation_ref for update in self.obligation_updates if update.operation != "create"],
            "revised obligation references",
        )
        return self


class ProposeQueue(_DecisionBase):
    type: Literal["propose_queue"]
    pending_tasks: list[PendingTaskProposal] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_proposal(self) -> "ProposeQueue":
        existing_ids: list[str] = []
        task_keys: list[str] = []
        action_keys: list[str] = []
        retry_ids: list[str] = []
        new_tasks: list[TaskProposal] = []
        for task in self.pending_tasks:
            if isinstance(task, ExistingTaskReference):
                existing_ids.append(task.task_id)
                continue
            new_tasks.append(task)
            task_keys.append(task.task_key)
            for action in task.actions:
                if isinstance(action, NewActionProposal):
                    action_keys.append(action.action_key)
                elif isinstance(action, RetryActionReference):
                    retry_ids.append(action.action_id)
        _unique(existing_ids, "existing task references")
        _unique(task_keys, "new task keys")
        _unique(action_keys, "new action keys")
        _unique(retry_ids, "retry action references")

        control_tasks = [task for task in new_tasks if task.type != "analysis"]
        if control_tasks and (len(self.pending_tasks) != 1 or self.obligation_check is None):
            raise ValueError("a new control task must be the sole queue entry and include obligation_check")
        if self.partial_authorization is not None and not (
            len(self.pending_tasks) == 1
            and isinstance(self.pending_tasks[0], TaskProposal)
            and self.pending_tasks[0].type == "answer"
        ):
            raise ValueError("partial_authorization requires a sole new answer task")
        return self


class StopDecision(_DecisionBase):
    type: Literal["stop"]
    reason_code: Literal[
        "insufficient_evidence", "unresolved_ambiguity", "no_progress", "cannot_complete",
    ]
    gap_refs: list[CanonicalUUID] = Field(max_length=32)

    @field_validator("gap_refs")
    @classmethod
    def unique_gaps(cls, value: list[str]) -> list[str]:
        return _unique(value, "gap_refs")

    @model_validator(mode="after")
    def validate_stop(self) -> "StopDecision":
        if self.obligation_check is None:
            raise ValueError("stop decisions require obligation_check")
        if self.partial_authorization is not None:
            raise ValueError("stop decisions cannot carry partial_authorization")
        return self


SupervisorDecision = Annotated[ProposeQueue | StopDecision, Field(discriminator="type")]
