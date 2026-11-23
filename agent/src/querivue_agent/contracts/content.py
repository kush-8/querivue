"""Strict structured answer content; support resolution remains a runtime concern."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .values import CanonicalUUID, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


def _utf8_limit(limit: int):
    def validate(value: str) -> str:
        if len(value.encode("utf-8")) > limit:
            raise ValueError(f"expected at most {limit} UTF-8 bytes")
        return value

    return validate


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]
BlockID = Annotated[NonblankString, AfterValidator(_utf8_limit(64))]
LiteralText = Annotated[UnicodeString, Field(min_length=1), AfterValidator(_utf8_limit(2048))]
DeliverableText = Annotated[NonblankString, AfterValidator(_utf8_limit(1024))]
StrictIndex = Annotated[int, Field(strict=True, ge=0)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CellTarget(_StrictModel):
    kind: Literal["cell"]
    evidence_id: CanonicalUUID
    row_locator: StrictIndex
    column_ordinal: StrictIndex


class MetadataTarget(_StrictModel):
    kind: Literal["metadata"]
    evidence_id: CanonicalUUID
    field: Literal["row_count"]


class CoverageTarget(_StrictModel):
    kind: Literal["coverage"]
    evidence_id: CanonicalUUID


class ChartTarget(_StrictModel):
    kind: Literal["chart"]
    chart_artifact_id: CanonicalUUID


class ContextTarget(_StrictModel):
    kind: Literal["context"]
    context_ref: CanonicalUUID


ValueTarget = Annotated[CellTarget | MetadataTarget, Field(discriminator="kind")]
SupportTarget = Annotated[
    CellTarget | MetadataTarget | CoverageTarget | ChartTarget | ContextTarget,
    Field(discriminator="kind"),
]


class TextSpan(_StrictModel):
    kind: Literal["text"]
    text: LiteralText


class ValueSpan(_StrictModel):
    kind: Literal["value"]
    target: ValueTarget
    format: Literal[
        "exact", "fixed_0", "fixed_1", "fixed_2", "percent_0", "percent_1",
        "percent_2", "currency_2", "iso",
    ]


class ChartSpan(_StrictModel):
    kind: Literal["chart"]
    chart_artifact_id: CanonicalUUID


ContentSpan = Annotated[TextSpan | ValueSpan | ChartSpan, Field(discriminator="kind")]
QuestionSpan = Annotated[TextSpan | ValueSpan, Field(discriminator="kind")]

ClarificationTarget = Annotated[
    CellTarget | MetadataTarget | ContextTarget,
    Field(discriminator="kind"),
]


class DraftBlock(_StrictModel):
    block_id: BlockID
    kind: Literal["data_claim", "general_explanation", "assumption", "limitation"]
    spans: list[ContentSpan] = Field(min_length=1, max_length=32)
    supports: list[SupportTarget]


class QuestionContent(_StrictModel):
    spans: list[QuestionSpan] = Field(min_length=1)
    supports: list[ClarificationTarget]


class Suggestion(_StrictModel):
    option_id: BlockID
    candidate_refs: list[BlockID] = Field(min_length=1)
    content: QuestionContent

    @field_validator("candidate_refs")
    @classmethod
    def unique_candidate_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_refs must be unique")
        return value


class UnmetDeliverable(_StrictModel):
    description: DeliverableText
    reason: DeliverableText
    required_evidence: DeliverableText


class Draft(_StrictModel):
    blocks: list[DraftBlock] = Field(min_length=1, max_length=16)
    unmet_deliverables: list[UnmetDeliverable] = Field(max_length=16)

    @field_validator("blocks")
    @classmethod
    def unique_block_ids(cls, value: list[DraftBlock]) -> list[DraftBlock]:
        if len({block.block_id for block in value}) != len(value):
            raise ValueError("block_id values must be unique")
        return value

    @model_validator(mode="after")
    def validate_aggregate_limits(self) -> "Draft":
        validate_block_aggregate_limits(self.blocks, subject="draft")
        return self


def validate_block_aggregate_limits(
    blocks: list[DraftBlock], *, subject: str,
) -> None:
    if sum(len(block.spans) for block in blocks) > 128:
        raise ValueError(f"{subject} may contain at most 128 spans")

    targets: set[tuple[object, ...]] = set()
    for block in blocks:
        for target in block.supports:
            targets.add(tuple(target.model_dump().items()))
        for span in block.spans:
            if isinstance(span, ValueSpan):
                targets.add(tuple(span.target.model_dump().items()))
            elif isinstance(span, ChartSpan):
                targets.add((("kind", "chart"), ("chart_artifact_id", span.chart_artifact_id)))
    if len(targets) > 128:
        raise ValueError(f"{subject} may reference at most 128 distinct targets")
