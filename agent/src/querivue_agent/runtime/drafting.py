"""Typed drafting system for answer specialist and reviewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.content import DraftBlock, QuestionSpan, SupportTarget, BlockID
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.contracts.budgets import BudgetSnapshot


# --- Display Format Types ---

DisplayFormat = Literal[
    "exact",
    "fixed_0", "fixed_1", "fixed_2",
    "percent_0", "percent_1", "percent_2",
    "currency_2",
    "iso",
]


@dataclass(frozen=True)
class ValueSpan:
    """A value span referencing a cell in evidence."""
    target: SupportTarget
    format: DisplayFormat
    value: Any  # The actual resolved value from evidence
    unit: str | None = None


@dataclass(frozen=True)
class ChartSpan:
    """A chart span referencing a chart artifact."""
    chart_artifact_id: CanonicalUUID
    caption: str | None = None


ContentSpan = (
    ValueSpan | ChartSpan | str  # str represents literal text
)


@dataclass(frozen=True)
class TypedDraftBlock:
    """A typed draft block with spans and supports."""
    block_id: BlockID
    kind: Literal["data_claim", "general_explanation", "assumption", "limitation"]
    spans: list[ContentSpan]
    supports: list[SupportTarget]

    def __post_init__(self):
        if not self.spans:
            raise ValueError("spans must be non-empty")
        if not self.block_id:
            raise ValueError("block_id must be non-empty")


@dataclass(frozen=True)
class UnmetDeliverable:
    """An unmet deliverable in a draft."""
    description: str
    reason: str
    required_evidence: str


@dataclass(frozen=True)
class TypedDraft:
    """A complete typed draft."""
    draft_id: CanonicalUUID
    blocks: list[TypedDraftBlock]
    unmet_deliverables: list[UnmetDeliverable] = field(default_factory=list)
    predecessor_draft_id: CanonicalUUID | None = None
    review_feedback_id: CanonicalUUID | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))

    def __post_init__(self):
        if not self.blocks:
            raise ValueError("blocks must be non-empty")
        block_ids = [b.block_id for b in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block_id values must be unique")


Completeness = Literal["complete", "partial"]


@dataclass(frozen=True)
class DraftReady:
    """Draft ready for review."""
    draft: TypedDraft
    completeness: Completeness


@dataclass(frozen=True)
class BlockedRequirement:
    """A requirement blocking draft completion."""
    kind: Literal["evidence", "definition", "conflict"]
    description: str


@dataclass(frozen=True)
class Blocked:
    """Draft blocked on missing requirements."""
    explanation: str
    requirements: list[BlockedRequirement]


@dataclass(frozen=True)
class Failed:
    """Draft failed due to runtime error."""
    error_ref: str
    stage: str


DraftOutcome = DraftReady | Blocked | Failed


# --- Review Types ---

FindingCategory = Literal["evidence", "draft"]


@dataclass(frozen=True)
class ReviewFinding:
    """A single blocking finding from review."""
    finding_id: BlockID
    category: FindingCategory
    affected_block_ids: list[BlockID] = field(default_factory=list)
    explanation: str = ""
    support_refs: list[SupportTarget] = field(default_factory=list)
    required_change: str = ""


@dataclass(frozen=True)
class ReviewedAssessment:
    """Reviewer assessment outcome."""
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    draft_content_hash: str
    draft_input_packet_hash: str
    rendering_policy_version: str
    review_pass: int
    approved: bool
    findings: list[ReviewFinding] = field(default_factory=list)

    def __post_init__(self):
        if self.approved and self.findings:
            raise ValueError("Approved review must have empty findings")
        if not self.approved and not self.findings:
            raise ValueError("Rejected review must have at least one finding")


ReviewVerdict = Literal["approved", "rejected"]


# --- Drafting Engine ---

class DraftingEngine:
    """Engine for creating and validating typed drafts."""

    def __init__(self, rendering_policy_version: str = "v1") -> None:
        self._rendering_policy_version = rendering_policy_version

    @property
    def rendering_policy_version(self) -> str:
        return self._rendering_policy_version

    def create_draft(
        self,
        blocks: list[TypedDraftBlock],
        unmet_deliverables: list[UnmetDeliverable] | None = None,
        predecessor_draft_id: CanonicalUUID | None = None,
        review_feedback_id: CanonicalUUID | None = None,
    ) -> TypedDraft:
        """Create a new draft."""
        return TypedDraft(
            draft_id=CanonicalUUID(str(uuid4())),
            blocks=blocks,
            unmet_deliverables=unmet_deliverables or [],
            predecessor_draft_id=predecessor_draft_id,
            review_feedback_id=review_feedback_id,
        )

    def validate_draft(self, draft: TypedDraft, evidence: dict[str, TabularEvidence]) -> list[str]:
        """Validate a draft against evidence. Returns list of validation errors."""
        errors = []

        # Check block ID uniqueness
        block_ids = [b.block_id for b in draft.blocks]
        if len(block_ids) != len(set(block_ids)):
            errors.append("Duplicate block_ids found")

        # Check each block
        for block in draft.blocks:
            # Validate spans
            for span in block.spans:
                if isinstance(span, ValueSpan):
                    errors.extend(self._validate_value_span(span, evidence))
                elif isinstance(span, ChartSpan):
                    errors.extend(self._validate_chart_span(span))

            # Validate supports
            for support in block.supports:
                errors.extend(self._validate_support(support, evidence))

        return errors

    def _validate_value_span(self, span: ValueSpan, evidence: dict[str, TabularEvidence]) -> list[str]:
        """Validate a value span."""
        errors = []
        target = span.target

        if not isinstance(target, dict):
            return ["Support target must be a dict"]

        target_type = target.get("type")
        if target_type == "cell":
            evidence_id = target.get("evidence_id")
            if evidence_id not in evidence:
                errors.append(f"Evidence {evidence_id} not found for cell reference")
            else:
                ev = evidence[evidence_id]
                row_locator = target.get("row_locator")
                column_ordinal = target.get("column_ordinal")
                if row_locator is not None and row_locator >= ev.row_count:
                    errors.append(f"Row locator {row_locator} out of bounds for evidence {evidence_id}")
                # column_ordinal validation would need schema

        elif target_type == "metadata":
            evidence_id = target.get("evidence_id")
            if evidence_id not in evidence:
                errors.append(f"Evidence {evidence_id} not found for metadata reference")

        return errors

    def _validate_chart_span(self, span: ChartSpan) -> list[str]:
        """Validate a chart span."""
        # Chart validation would check against input.charts
        return []

    def _validate_support(self, support: SupportTarget, evidence: dict[str, TabularEvidence]) -> list[str]:
        """Validate a support target."""
        errors = []

        if not isinstance(support, dict):
            return ["Support target must be a dict"]

        target_type = support.get("type")
        if target_type in ("cell", "metadata"):
            evidence_id = support.get("evidence_id")
            if evidence_id not in evidence:
                errors.append(f"Evidence {evidence_id} not found for support reference")

        return errors

    def render_draft(self, draft: TypedDraft, evidence: dict[str, TabularEvidence]) -> str:
        """Render a draft to text transcript."""
        lines = []
        for block in draft.blocks:
            block_text = self._render_block(block, evidence)
            lines.append(f"[{block.kind}:{block.block_id}] {block_text}")

        if draft.unmet_deliverables:
            lines.append("\n--- Unmet Deliverables ---")
            for i, ud in enumerate(draft.unmet_deliverables, 1):
                lines.append(f"{i}. {ud.description} ({ud.reason})")

        return "\n".join(lines)

    def _render_block(self, block: TypedDraftBlock, evidence: dict[str, TabularEvidence]) -> str:
        """Render a single block."""
        parts = []
        for span in block.spans:
            if isinstance(span, str):
                parts.append(span)
            elif isinstance(span, ValueSpan):
                parts.append(self._render_value(span, evidence))
            elif isinstance(span, ChartSpan):
                parts.append(f"[Chart:{span.chart_artifact_id}]")
        return " ".join(parts)

    def _render_value(self, span: ValueSpan, evidence: dict[str, TabularEvidence]) -> str:
        """Render a value with its format."""
        value = span.value
        fmt = span.format

        if value is None:
            return "[missing]"

        if fmt == "exact":
            return str(value)
        elif fmt.startswith("fixed_"):
            precision = int(fmt.split("_")[1])
            if isinstance(value, (int, float)):
                return f"{value:.{precision}f}"
            return str(value)
        elif fmt.startswith("percent_"):
            precision = int(fmt.split("_")[1])
            if isinstance(value, (int, float)):
                return f"{value * 100:.{precision}f}%"
            return str(value)
        elif fmt == "currency_2":
            if isinstance(value, (int, float)):
                return f"${value:.2f}"
            return str(value)
        elif fmt == "iso":
            return str(value)
        else:
            return str(value)


def create_value_span(
    evidence_id: CanonicalUUID,
    row_locator: int,
    column_ordinal: int,
    value: Any,
    format: DisplayFormat,
    unit: str | None = None,
) -> ValueSpan:
    """Create a value span from evidence reference."""
    return ValueSpan(
        target={
            "type": "cell",
            "evidence_id": str(evidence_id),
            "row_locator": row_locator,
            "column_ordinal": column_ordinal,
        },
        format=format,
        value=value,
        unit=unit,
    )


def create_chart_span(
    chart_artifact_id: CanonicalUUID,
    caption: str | None = None,
) -> ChartSpan:
    """Create a chart span."""
    return ChartSpan(
        chart_artifact_id=chart_artifact_id,
        caption=caption,
    )


def create_block(
    block_id: BlockID,
    kind: Literal["data_claim", "general_explanation", "assumption", "limitation"],
    spans: list[ContentSpan],
    supports: list[SupportTarget],
) -> TypedDraftBlock:
    """Create a typed draft block."""
    return TypedDraftBlock(
        block_id=block_id,
        kind=kind,
        spans=spans,
        supports=supports,
    )