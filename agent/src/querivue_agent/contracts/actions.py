"""Strict shape validation for planned analysis actions."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .content import (
    BlockID, ClarificationTarget, DraftBlock, validate_block_aggregate_limits,
)
from .values import CanonicalUUID, RuntimeUUID, TypedScalar, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", exclude_none=True)


class DateWindow(_StrictModel):
    source_id: CanonicalUUID
    column: NonblankString
    lower: TypedScalar
    upper: TypedScalar
    lower_inclusive: bool
    upper_inclusive: bool


class AnalysisConstraints(_StrictModel):
    metric_definitions: dict[NonblankString, NonblankString]
    filters: list[NonblankString]
    date_windows: list[DateWindow]
    analysis_timezone: NonblankString | None
    grain: NonblankString | None
    units: dict[NonblankString, NonblankString]


class _ActionRequest(_StrictModel):
    objective: NonblankString
    constraints: AnalysisConstraints


class SQLRequest(_ActionRequest):
    type: Literal["sql"]
    table_ids: list[CanonicalUUID]
    input_evidence_ids: list[CanonicalUUID]

    @field_validator("table_ids", "input_evidence_ids")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("input references must be unique")
        return value

    @model_validator(mode="after")
    def require_input(self) -> "SQLRequest":
        if not self.table_ids and not self.input_evidence_ids:
            raise ValueError("at least one table or evidence input is required")
        return self


class SQLAction(SQLRequest):
    action_id: RuntimeUUID


class PythonRequest(_ActionRequest):
    type: Literal["python"]
    input_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    required_outputs: list[Literal["evidence", "chart"]] = Field(min_length=1)

    @field_validator("input_evidence_ids", "required_outputs")
    @classmethod
    def unique_items(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("items must be unique")
        return value


class PythonAction(PythonRequest):
    action_id: RuntimeUUID


class AnswerRequest(_ActionRequest):
    type: Literal["answer"]
    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]

    @field_validator("evidence_ids", "chart_artifact_ids")
    @classmethod
    def unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("references must be unique")
        return value


class AnswerAction(AnswerRequest):
    action_id: RuntimeUUID
    draft_id: CanonicalUUID | None = Field(default=None, exclude=True)


class DirectAnswerRequest(_StrictModel):
    type: Literal["direct_answer"]
    basis: Literal["knowledge", "evidence"]
    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]
    context_refs: list[CanonicalUUID]
    blocks: list[DraftBlock] = Field(min_length=1, max_length=16)

    @field_validator("evidence_ids", "chart_artifact_ids", "context_refs")
    @classmethod
    def unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("references must be unique")
        return value

    @field_validator("blocks")
    @classmethod
    def unique_block_ids(cls, value: list[DraftBlock]) -> list[DraftBlock]:
        if len({block.block_id for block in value}) != len(value):
            raise ValueError("block_id values must be unique")
        return value

    @model_validator(mode="after")
    def validate_aggregate_limits(self) -> "DirectAnswerRequest":
        validate_block_aggregate_limits(self.blocks, subject="direct answer")
        return self


class DirectAnswer(DirectAnswerRequest):
    action_id: RuntimeUUID


class CandidateInterpretation(_StrictModel):
    candidate_id: BlockID
    interpretation: NonblankString
    basis_refs: list[ClarificationTarget]


class ClarificationRequest(_StrictModel):
    type: Literal["clarify"]
    issue: NonblankString
    candidate_interpretations: list[CandidateInterpretation]
    constraints: AnalysisConstraints
    input_evidence_ids: list[CanonicalUUID]
    context_refs: list[CanonicalUUID]

    @field_validator("input_evidence_ids", "context_refs")
    @classmethod
    def unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("references must be unique")
        return value

    @field_validator("candidate_interpretations")
    @classmethod
    def unique_candidate_ids(
        cls, value: list[CandidateInterpretation],
    ) -> list[CandidateInterpretation]:
        if len({candidate.candidate_id for candidate in value}) != len(value):
            raise ValueError("candidate_id values must be unique")
        return value


class ClarificationAction(ClarificationRequest):
    action_id: RuntimeUUID


ActionRequest = Annotated[
    SQLRequest | PythonRequest | AnswerRequest | DirectAnswerRequest | ClarificationRequest,
    Field(discriminator="type"),
]


Action = Annotated[
    SQLAction | PythonAction | AnswerAction | DirectAnswer | ClarificationAction,
    Field(discriminator="type"),
]


StrictPositiveSafeInteger = Annotated[
    int, Field(strict=True, ge=1, le=9007199254740991),
]


class TaskPrerequisite(_StrictModel):
    action_id: CanonicalUUID
    expected_attempt: StrictPositiveSafeInteger


class Task(_StrictModel):
    task_id: RuntimeUUID
    type: Literal["analysis", "answer", "clarify", "direct_answer"]
    requires: list[TaskPrerequisite] = Field(max_length=4)
    actions: list[Action] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_task(self) -> "Task":
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action_id values must be unique")

        prerequisite_ids = [prerequisite.action_id for prerequisite in self.requires]
        if len(prerequisite_ids) != len(set(prerequisite_ids)):
            raise ValueError("prerequisite action_id values must be unique")
        if set(action_ids) & set(prerequisite_ids):
            raise ValueError("a task cannot require one of its own actions")

        if self.type == "analysis":
            if len(self.actions) > 2:
                raise ValueError("analysis tasks may contain at most 2 actions")
            if not all(isinstance(action, (SQLAction, PythonAction)) for action in self.actions):
                raise ValueError("analysis tasks may contain only sql or python actions")
        else:
            expected = {
                "answer": AnswerAction,
                "clarify": ClarificationAction,
                "direct_answer": DirectAnswer,
            }[self.type]
            if len(self.actions) != 1 or not isinstance(self.actions[0], expected):
                raise ValueError(f"{self.type} tasks require exactly one matching action")
        return self


class NewActionProposal(_StrictModel):
    kind: Literal["new_action"]
    action_key: BlockID
    request: ActionRequest


class RetryActionReference(_StrictModel):
    kind: Literal["retry_action"]
    action_id: CanonicalUUID
    failed_attempt: StrictPositiveSafeInteger
    result_ref: CanonicalUUID


ProposedAction = Annotated[
    NewActionProposal | RetryActionReference,
    Field(discriminator="kind"),
]


class TaskProposal(_StrictModel):
    kind: Literal["new_task"]
    task_key: BlockID
    type: Literal["analysis", "answer", "clarify", "direct_answer"]
    requires: list[TaskPrerequisite] = Field(max_length=4)
    actions: list[ProposedAction] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_task(self) -> "TaskProposal":
        new_actions = [action for action in self.actions if isinstance(action, NewActionProposal)]
        action_keys = [action.action_key for action in new_actions]
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("action_key values must be unique")

        retries = [action for action in self.actions if isinstance(action, RetryActionReference)]
        retry_ids = [action.action_id for action in retries]
        if len(retry_ids) != len(set(retry_ids)):
            raise ValueError("retry action_id values must be unique")

        prerequisite_ids = [prerequisite.action_id for prerequisite in self.requires]
        if len(prerequisite_ids) != len(set(prerequisite_ids)):
            raise ValueError("prerequisite action_id values must be unique")
        if set(retry_ids) & set(prerequisite_ids):
            raise ValueError("a task proposal cannot require one of its retry actions")

        if self.type == "analysis":
            if len(self.actions) > 2:
                raise ValueError("analysis task proposals may contain at most 2 actions")
            if not all(
                isinstance(action, RetryActionReference)
                or isinstance(action.request, (SQLRequest, PythonRequest))
                for action in self.actions
            ):
                raise ValueError("analysis task proposals may contain only sql or python requests")
        else:
            if len(self.actions) != 1:
                raise ValueError(f"{self.type} task proposals require exactly one action")
            action = self.actions[0]
            if isinstance(action, RetryActionReference):
                if self.type != "answer":
                    raise ValueError("retry actions are allowed only in analysis or answer tasks")
            else:
                expected = {
                    "answer": AnswerRequest,
                    "clarify": ClarificationRequest,
                    "direct_answer": DirectAnswerRequest,
                }[self.type]
                if not isinstance(action.request, expected):
                    raise ValueError(f"{self.type} task proposals require a matching request")
        return self


class ExistingTaskReference(_StrictModel):
    kind: Literal["existing_task"]
    task_id: CanonicalUUID


PendingTaskProposal = Annotated[
    TaskProposal | ExistingTaskReference,
    Field(discriminator="kind"),
]
