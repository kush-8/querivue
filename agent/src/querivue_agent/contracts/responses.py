"""Shape validation only: callers must supply runtime-sanitized, verified errors
and authorized, published evidence valid for the current scope and source.
"""

from typing import Annotated, Literal

import re

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, ValidationInfo, field_validator,
    model_validator,
)

from .content import BlockID, Draft, QuestionContent, Suggestion, SupportTarget, ValueSpan
from .values import CanonicalUUID, RuntimeUUID, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]

ErrorCode = Literal[
    "invalid_arguments", "sql_parse_error", "unknown_relation", "unknown_column",
    "type_mismatch", "policy_violation", "sql_unsupported", "source_unavailable",
    "artifact_unavailable", "artifact_integrity_failure", "query_timeout",
    "result_limit_exceeded", "unsupported_result_type", "infrastructure_unavailable",
    "budget_exhausted", "no_progress", "invalid_specialist_output", "internal_error",
]
ErrorStage = Literal["validation", "execution", "persistence", "recovery"]
ErrorDisposition = Literal[
    "correct_query", "retry_operation", "clarify", "replan", "fail_action", "invalidate_run",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ToolError(_StrictModel):
    code: ErrorCode
    message: Annotated[NonblankString, Field(max_length=2048)]
    stage: ErrorStage
    operation_id: RuntimeUUID | None = None
    disposition: ErrorDisposition


class _SQLOutcome(_StrictModel):
    evidence_ids: list[CanonicalUUID]

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class SQLSucceeded(_SQLOutcome):
    status: Literal["succeeded"]
    observation: NonblankString
    evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    limitations: list[NonblankString]


class SQLBlocked(_SQLOutcome):
    status: Literal["blocked"]
    explanation: NonblankString
    required_input: NonblankString


class SQLFailed(_SQLOutcome):
    status: Literal["failed"]
    error: ToolError


SQLOutcome = Annotated[SQLSucceeded | SQLBlocked | SQLFailed, Field(discriminator="status")]


class _PythonOutcome(_StrictModel):
    """Shape boundary only; runtime output and authorization checks happen elsewhere."""

    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]

    @field_validator("evidence_ids", "chart_artifact_ids")
    @classmethod
    def unique_references(cls, value: list[str], info: ValidationInfo) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value


class PythonSucceeded(_PythonOutcome):
    status: Literal["succeeded"]
    observation: NonblankString
    limitations: list[NonblankString]


class PythonBlocked(_PythonOutcome):
    status: Literal["blocked"]
    explanation: NonblankString
    required_input: NonblankString


class PythonFailed(_PythonOutcome):
    status: Literal["failed"]
    error: ToolError


PythonOutcome = Annotated[
    PythonSucceeded | PythonBlocked | PythonFailed,
    Field(discriminator="status"),
]


class AnswerDraftReady(_StrictModel):
    status: Literal["draft_ready"]
    draft: Draft
    completeness: Literal["complete", "partial"]


class Requirement(_StrictModel):
    kind: Literal["evidence", "definition", "conflict"]
    description: NonblankString


class AnswerBlocked(_StrictModel):
    status: Literal["blocked"]
    explanation: NonblankString
    requirements: list[Requirement] = Field(min_length=1)


class AnswerFailed(_StrictModel):
    status: Literal["failed"]
    error_ref: CanonicalUUID


AnswerOutcome = Annotated[
    AnswerDraftReady | AnswerBlocked | AnswerFailed,
    Field(discriminator="status"),
]


class ClarificationQuestionReady(_StrictModel):
    status: Literal["question_ready"]
    question: QuestionContent
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_question(self) -> "ClarificationQuestionReady":
        if self.suggestions and len(self.suggestions) < 2:
            raise ValueError("suggestions must be empty or contain 2 to 4 items")
        if len({suggestion.option_id for suggestion in self.suggestions}) != len(self.suggestions):
            raise ValueError("option_id values must be unique")

        contents = [self.question, *(suggestion.content for suggestion in self.suggestions)]
        if sum(len(content.spans) for content in contents) > 32:
            raise ValueError("clarification response may contain at most 32 spans")
        reference_count = sum(
            len(content.supports)
            + sum(isinstance(span, ValueSpan) for span in content.spans)
            for content in contents
        )
        if reference_count > 32:
            raise ValueError(
                "clarification response may contain at most 32 support-reference occurrences"
            )
        return self


class ClarificationBlocked(_StrictModel):
    status: Literal["blocked"]
    explanation: NonblankString
    required_input: NonblankString


class ClarificationFailed(_StrictModel):
    status: Literal["failed"]
    error_ref: CanonicalUUID


ClarificationOutcome = Annotated[
    ClarificationQuestionReady | ClarificationBlocked | ClarificationFailed,
    Field(discriminator="status"),
]


def _hash(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("expected 64 lowercase hexadecimal characters")
    return value


ContentHash = Annotated[str, Field(strict=True), AfterValidator(_hash)]
ReviewPass = Annotated[int, Field(strict=True, ge=1, le=2)]


class ReviewFinding(_StrictModel):
    finding_id: BlockID
    category: Literal["evidence", "draft"]
    block_ids: list[BlockID]
    explanation: NonblankString
    support_refs: list[SupportTarget]
    required_change: NonblankString

    @field_validator("block_ids")
    @classmethod
    def unique_block_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("block_ids must be unique")
        return value


class ReviewBinding(_StrictModel):
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    draft_content_hash: ContentHash
    draft_input_packet_hash: ContentHash
    review_input_packet_hash: ContentHash
    rendering_policy_version: NonblankString
    review_pass: ReviewPass


class ReviewedAssessment(ReviewBinding):
    status: Literal["reviewed"]
    verdict: Literal["approved", "rejected"]
    findings: list[ReviewFinding]

    @model_validator(mode="after")
    def validate_findings(self) -> "ReviewedAssessment":
        if (self.verdict == "approved" and self.findings) or (
            self.verdict == "rejected" and not self.findings
        ):
            raise ValueError("approved requires no findings and rejected requires findings")
        if len({finding.finding_id for finding in self.findings}) != len(self.findings):
            raise ValueError("finding_id values must be unique")
        return self


class CannotCompleteAssessment(_StrictModel):
    status: Literal["cannot_complete"]
    explanation: NonblankString


ReviewAssessment = Annotated[
    ReviewedAssessment | CannotCompleteAssessment,
    Field(discriminator="status"),
]


class ReviewFailed(ReviewBinding):
    status: Literal["failed"]
    error_ref: CanonicalUUID


ReviewOutcome = Annotated[
    ReviewedAssessment | ReviewFailed,
    Field(discriminator="status"),
]
