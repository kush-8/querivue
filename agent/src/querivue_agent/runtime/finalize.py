"""Final rendering of approved candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from querivue_agent.contracts.records import FinalCandidate, ReviewedCandidate, DirectCandidate
from querivue_agent.contracts.content import DraftBlock, ContentSpan, ValueSpan, ChartSpan, TextSpan
from querivue_agent.contracts.values import CanonicalUUID

if TYPE_CHECKING:
    from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact


def render(candidate: FinalCandidate) -> str:
    """Render a FinalCandidate to its final text representation."""
    if isinstance(candidate, ReviewedCandidate):
        return _render_reviewed_candidate(candidate)
    elif isinstance(candidate, DirectCandidate):
        return _render_direct_candidate(candidate)
    else:
        raise ValueError(f"Unknown candidate kind: {type(candidate)}")


def _render_reviewed_candidate(candidate: ReviewedCandidate) -> str:
    """Render a reviewed candidate (draft that passed review)."""
    lines = []

    # Render each block
    for block in candidate.draft.blocks:
        block_text = _render_block(block)
        lines.append(block_text)

    # Add unmet deliverables if partial
    if candidate.completeness == "partial" and candidate.draft.unmet_deliverables:
        lines.append("")  # blank line before unmet section
        lines.append("---")
        lines.append("**Unmet Deliverables**")
        for i, ud in enumerate(candidate.draft.unmet_deliverables, 1):
            lines.append(f"{i}. {ud.description} — {ud.reason}")

    return "\n".join(lines)


def _render_direct_candidate(candidate: DirectCandidate) -> str:
    """Render a direct answer candidate."""
    lines = []

    for block in candidate.action.blocks:
        block_text = _render_direct_block(block)
        lines.append(block_text)

    return "\n".join(lines)


def _render_block(block: DraftBlock) -> str:
    """Render a draft block to text."""
    parts = []
    for span in block.spans:
        if isinstance(span, TextSpan):
            parts.append(span.text)
        elif isinstance(span, ValueSpan):
            parts.append(_render_value_span(span))
        elif isinstance(span, ChartSpan):
            parts.append(f"[Chart: {span.chart_artifact_id}]")
        else:
            # Fallback for any unrecognized span type
            parts.append(str(span))
    return " ".join(parts)


def _render_direct_block(block: DraftBlock) -> str:
    """Render a direct answer block (same as reviewed for now)."""
    return _render_block(block)


def _render_value_span(span: ValueSpan) -> str:
    """Render a value span with its format."""
    # We need the actual value from evidence - for now just render the target reference
    target = span.target
    fmt = span.format

    if hasattr(target, 'kind') and target.kind == "cell":
        # For final rendering, we'd resolve the actual value from evidence
        # For now, render a placeholder with format info
        return f"[{target.evidence_id}:{target.row_locator}:{target.column_ordinal} ({fmt})]"
    elif hasattr(target, 'kind') and target.kind == "metadata":
        return f"[{target.evidence_id}.{target.field} ({fmt})]"
    else:
        return f"[value:{span.format}]"


# For rendering with actual evidence values, we need a more complete version
def render_with_evidence(
    candidate: FinalCandidate,
    evidence: dict[str, "TabularEvidence"],
    charts: dict[str, "ChartArtifact"],
) -> str:
    """Render a FinalCandidate with actual evidence values resolved."""
    if isinstance(candidate, ReviewedCandidate):
        return _render_reviewed_candidate_with_evidence(candidate, evidence, charts)
    elif isinstance(candidate, DirectCandidate):
        return _render_direct_candidate_with_evidence(candidate, evidence, charts)
    else:
        raise ValueError(f"Unknown candidate kind: {type(candidate)}")


def _render_reviewed_candidate_with_evidence(
    candidate: ReviewedCandidate,
    evidence: dict[str, "TabularEvidence"],
    charts: dict[str, "ChartArtifact"],
) -> str:
    """Render a reviewed candidate with evidence values."""
    lines = []

    for block in candidate.draft.blocks:
        block_text = _render_block_with_evidence(block, evidence, charts)
        lines.append(block_text)

    if candidate.completeness == "partial" and candidate.draft.unmet_deliverables:
        lines.append("")
        lines.append("---")
        lines.append("**Unmet Deliverables**")
        for i, ud in enumerate(candidate.draft.unmet_deliverables, 1):
            lines.append(f"{i}. {ud.description} — {ud.reason}")

    return "\n".join(lines)


def _render_direct_candidate_with_evidence(
    candidate: DirectCandidate,
    evidence: dict[str, "TabularEvidence"],
    charts: dict[str, "ChartArtifact"],
) -> str:
    """Render a direct candidate with evidence values."""
    lines = []

    for block in candidate.action.blocks:
        block_text = _render_block_with_evidence(block, evidence, charts)
        lines.append(block_text)

    return "\n".join(lines)


def _render_block_with_evidence(
    block: DraftBlock,
    evidence: dict[str, "TabularEvidence"],
    charts: dict[str, "ChartArtifact"],
) -> str:
    """Render a block with evidence values resolved."""
    parts = []
    for span in block.spans:
        if isinstance(span, TextSpan):
            parts.append(span.text)
        elif isinstance(span, ValueSpan):
            parts.append(_render_value_span_with_evidence(span, evidence))
        elif isinstance(span, ChartSpan):
            parts.append(_render_chart_span_with_evidence(span, charts))
        else:
            parts.append(str(span))
    return " ".join(parts)


def _render_value_span_with_evidence(
    span: ValueSpan,
    evidence: dict[str, "TabularEvidence"],
) -> str:
    """Render a value span with actual value from evidence."""
    target = span.target
    fmt = span.format

    if target.kind == "cell":
        ev = evidence.get(target.evidence_id)
        if ev is None:
            return f"[missing evidence {target.evidence_id}]"

        # Get the actual value from the evidence
        # This would need to read the parquet file or use preview data
        # For now, we use the preview rows if available
        if ev.preview.rows and target.row_locator < len(ev.preview.rows):
            row = ev.preview.rows[target.row_locator]
            if target.column_ordinal < len(row):
                value = row[target.column_ordinal]
            else:
                value = None
        else:
            value = None

        return _format_value(value, fmt, span.target.unit if hasattr(span.target, 'unit') else None)

    elif target.kind == "metadata":
        ev = evidence.get(target.evidence_id)
        if ev is None:
            return f"[missing evidence {target.evidence_id}]"

        if target.field == "row_count":
            value = ev.row_count
        else:
            value = None

        return _format_value(value, fmt)

    return f"[unresolved value]"


def _render_chart_span_with_evidence(
    span: ChartSpan,
    charts: dict[str, "ChartArtifact"],
) -> str:
    """Render a chart span with chart info."""
    chart = charts.get(str(span.chart_artifact_id))
    if chart is None:
        return f"[Chart: {span.chart_artifact_id} (not found)]"

    caption = span.caption or chart.spec.title if hasattr(chart, 'spec') else ""
    return f"[Chart: {span.chart_artifact_id} — {caption}]"


def _format_value(value: any, fmt: str, unit: str | None = None) -> str:
    """Format a value according to the display format."""
    if value is None:
        return "[null]"

    # Try to convert string numeric values to numbers for formatting
    if isinstance(value, str):
        try:
            if '.' in value:
                value = float(value)
            else:
                value = int(value)
        except ValueError:
            pass  # Keep as string if not numeric

    if fmt == "exact":
        result = str(value)
    elif fmt.startswith("fixed_"):
        precision = int(fmt.split("_")[1])
        if isinstance(value, (int, float)):
            result = f"{value:.{precision}f}"
        else:
            result = str(value)
    elif fmt.startswith("percent_"):
        precision = int(fmt.split("_")[1])
        if isinstance(value, (int, float)):
            result = f"{value * 100:.{precision}f}%"
        else:
            result = str(value)
    elif fmt == "currency_2":
        if isinstance(value, (int, float)):
            result = f"${value:,.2f}"
        else:
            result = str(value)
    elif fmt == "iso":
        result = str(value)
    else:
        result = str(value)

    if unit:
        result = f"{result} {unit}"

    return result