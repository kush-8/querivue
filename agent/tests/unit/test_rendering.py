"""Unit tests for final rendering."""

from __future__ import annotations

from uuid import uuid4

import pytest

from querivue_agent.contracts.records import (
    ReviewedCandidate, DirectCandidate, AnswerResult, NoticeResult,
    FinalCandidate,
)
from querivue_agent.contracts.content import (
    DraftBlock, TextSpan, ValueSpan, ChartSpan, CellTarget, ChartTarget,
    Draft, UnmetDeliverable,
)
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
from querivue_agent.contracts.responses import (
    ReviewedAssessment, ReviewFinding, ReviewBinding,
    ContentHash, ReviewPass,
)
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.artifacts import ArtifactRef
from querivue_agent.contracts.artifacts import SourceDependency
from querivue_agent.runtime.finalize import (
    render, render_with_evidence, _format_value,
)


def create_mock_evidence(evidence_id: CanonicalUUID, row_count: int = 10) -> TabularEvidence:
    """Create mock tabular evidence for testing."""
    from querivue_agent.contracts.evidence import (
        EvidenceColumn, TabularPreview, Producer, SourceDependency,
        Int64Column, StringColumn, SQLProducer,
    )
    from querivue_agent.contracts.common import SafeCount, PositiveCount
    from querivue_agent.contracts.actions import AnalysisConstraints

    manifest_id = CanonicalUUID(str(uuid4()))

    return TabularEvidence(
        evidence_id=evidence_id,
        content_hash="a" * 64,
        artifact=ArtifactRef(
            artifact_id=CanonicalUUID(str(uuid4())),
            storage_ref=CanonicalUUID(str(uuid4())),
            media_type="application/vnd.apache.parquet",
            size_bytes=1000,
            sha256="a" * 64,
            environment_manifest_id=manifest_id,
        ),
        columns=[
            EvidenceColumn(ordinal=0, name="col1", original_label="col1", original_ordinal=0, type=Int64Column(tag="int64"), nullable=False),
            EvidenceColumn(ordinal=1, name="col2", original_label="col2", original_ordinal=1, type=StringColumn(tag="string"), nullable=False),
        ],
        row_count=row_count,
        preview=TabularPreview(
            columns=[
                EvidenceColumn(ordinal=0, name="col1", original_label="col1", original_ordinal=0, type=Int64Column(tag="int64"), nullable=False),
                EvidenceColumn(ordinal=1, name="col2", original_label="col2", original_ordinal=1, type=StringColumn(tag="string"), nullable=False),
            ],
            rows=[["100", "Region A"], ["200", "Region B"]],
            row_locators=[0, 1],
            full_row_count=row_count,
            returned_row_count=SafeCount(2),
            effective_limit=PositiveCount(100),
            ordering="unspecified",
            truncated=True,
            shortened_cells=[],
        ),
        producer=SQLProducer(
            kind="sql",
            run_id=CanonicalUUID(str(uuid4())),
            action_id=CanonicalUUID(str(uuid4())),
            operation_id=CanonicalUUID(str(uuid4())),
            attempt=PositiveCount(1),
            sql="SELECT * FROM test",
            parameters={},
            table_ids=[CanonicalUUID(str(uuid4()))],
            input_evidence_ids=[CanonicalUUID(str(uuid4()))],
            constraints=AnalysisConstraints(
                metric_definitions={"count": "count(*)"},
                filters=[],
                date_windows=[],
                analysis_timezone="UTC",
                grain="day",
                units={"count": "rows"},
            ),
            environment_manifest_id=manifest_id,
            policy_version="v1",
        ),
        dependencies=[
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
        ],
    )


def create_mock_chart(chart_id: CanonicalUUID) -> ChartArtifact:
    """Create mock chart artifact for testing."""
    from querivue_agent.contracts.artifacts import ArtifactRef, SourceDependency
    from querivue_agent.contracts.common import PositiveCount
    from querivue_agent.contracts.evidence import ChartArtifact, ChartDeclaration, ChartSeries, ColumnOrdering, Identifier, NonblankString, PythonProducer

    return ChartArtifact(
        chart_artifact_id=chart_id,
        artifact=ArtifactRef(
            artifact_id=chart_id,
            storage_ref=CanonicalUUID(str(uuid4())),
            media_type="image/png",
            size_bytes=500,
            sha256="b" * 64,
            environment_manifest_id=CanonicalUUID(str(uuid4())),
        ),
        declaration=ChartDeclaration(
            name=Identifier("sales_chart"),
            kind="chart",
            title="Sales by Region",
            description="Sales data by region",
            series=[
                ChartSeries(
                    label="sales",
                    evidence_id=CanonicalUUID(str(uuid4())),
                    ordering=[],
                    scales={"sales": "linear"},
                    columns={"sales": "sales"},
                )
            ],
            units={"sales": "USD"},
            analysis_timezone="UTC",
            limitations=[],
        ),
        producer=PythonProducer(
            kind="python",
            run_id=CanonicalUUID(str(uuid4())),
            action_id=CanonicalUUID(str(uuid4())),
            operation_id=CanonicalUUID(str(uuid4())),
            attempt=PositiveCount(1),
            code="chart_code",
            parameters={},
            input_evidence_ids=[CanonicalUUID(str(uuid4()))],
            environment_manifest_id=CanonicalUUID(str(uuid4())),
            policy_version="v1",
        ),
        pixel_width=800,
        pixel_height=600,
        encoder_version="v1",
        normalization_version="v1",
        backing_evidence_ids=[CanonicalUUID(str(uuid4()))],
        dependencies=[
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
        ],
    )


def create_reviewed_candidate() -> ReviewedCandidate:
    """Create a sample reviewed candidate for testing."""
    draft_id = CanonicalUUID(str(uuid4()))
    review_id = CanonicalUUID(str(uuid4()))

    block = DraftBlock(
        block_id="b1",
        kind="data_claim",
        spans=[
            TextSpan(kind="text", text="Revenue was "),
            ValueSpan(
                kind="value",
                target=CellTarget(
                    kind="cell",
                    evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
                    row_locator=0,
                    column_ordinal=0,
                ),
                format="currency_2",
            ),
        ],
        supports=[
            CellTarget(
                kind="cell",
                evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
                row_locator=0,
                column_ordinal=0,
            ),
        ],
    )

    draft = Draft(
        blocks=[block],
        unmet_deliverables=[],
    )

    review = ReviewedAssessment(
        review_id=review_id,
        draft_id=draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        review_input_packet_hash="c" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        verdict="approved",
        findings=[],
        status="reviewed",
    )

    return ReviewedCandidate(
        candidate_id=RuntimeUUID(str(uuid4())),
        scope={"run_id": CanonicalUUID(str(uuid4())), "chat_id": CanonicalUUID(str(uuid4())), "project_id": CanonicalUUID(str(uuid4())), "eligible_dataset_ids": []},
        content_hash="a" * 64,
        rendered_text="Revenue was $100.00",
        rendering_policy_version="v1",
        dependencies=[],
        source_input_hash="b" * 64,
        valid_until="2026-12-31T23:59:59Z",
        originating_invocation_id=CanonicalUUID(str(uuid4())),
        kind="reviewed",
        draft_id=draft_id,
        draft=draft,
        completeness="complete",
        review=review,
        approval_ref=review_id,
    )


def create_direct_candidate() -> DirectCandidate:
    """Create a sample direct candidate for testing."""
    from querivue_agent.contracts.actions import DirectAnswer

    action = DirectAnswer(
        type="direct_answer",
        basis="knowledge",
        evidence_ids=[],
        chart_artifact_ids=[],
        context_refs=[],
        blocks=[
            DraftBlock(
                block_id="b1",
                kind="general_explanation",
                spans=[
                    TextSpan(kind="text", text="Based on general knowledge, the answer is 42."),
                ],
                supports=[],
            ),
        ],
        action_id=RuntimeUUID(str(uuid4())),
    )

    return DirectCandidate(
        candidate_id=RuntimeUUID(str(uuid4())),
        scope={"run_id": CanonicalUUID(str(uuid4())), "chat_id": CanonicalUUID(str(uuid4())), "project_id": CanonicalUUID(str(uuid4())), "eligible_dataset_ids": []},
        content_hash="d" * 64,
        rendered_text="Based on general knowledge, the answer is 42.",
        rendering_policy_version="v1",
        dependencies=[],
        source_input_hash="e" * 64,
        valid_until="2026-12-31T23:59:59Z",
        originating_invocation_id=CanonicalUUID(str(uuid4())),
        kind="direct",
        action=action,
        completeness="complete",
        review_status="not_required_direct",
    )


def test_render_reviewed_candidate():
    """Test rendering a reviewed candidate."""
    candidate = create_reviewed_candidate()
    rendered = render(candidate)

    assert "Revenue was" in rendered
    assert "$100.00" in rendered or "currency_2" in rendered  # Either formatted or placeholder


def test_render_direct_candidate():
    """Test rendering a direct candidate."""
    candidate = create_direct_candidate()
    rendered = render(candidate)

    assert "Based on general knowledge" in rendered
    assert "42" in rendered


def test_render_reviewed_candidate_partial():
    """Test rendering a reviewed candidate with unmet deliverables."""
    candidate = create_reviewed_candidate()

    # Add unmet deliverable
    draft = candidate.draft
    new_draft = Draft(
        blocks=draft.blocks,
        unmet_deliverables=[
            UnmetDeliverable(
                description="Missing chart",
                reason="Chart generation failed",
                required_evidence="Chart artifact",
            ),
        ],
    )

    # Create new candidate with updated draft
    from copy import deepcopy
    new_candidate = deepcopy(candidate)
    new_candidate = ReviewedCandidate(
        candidate_id=new_candidate.candidate_id,
        scope=new_candidate.scope,
        content_hash=new_candidate.content_hash,
        rendered_text=new_candidate.rendered_text,
        rendering_policy_version=new_candidate.rendering_policy_version,
        dependencies=new_candidate.dependencies,
        source_input_hash=new_candidate.source_input_hash,
        valid_until=new_candidate.valid_until,
        originating_invocation_id=new_candidate.originating_invocation_id,
        kind="reviewed",
        draft_id=new_candidate.draft_id,
        draft=new_draft,
        completeness="partial",
        review=new_candidate.review,
        approval_ref=new_candidate.approval_ref,
    )

    rendered = render(new_candidate)
    assert "Unmet Deliverables" in rendered
    assert "Missing chart" in rendered
    assert "Chart generation failed" in rendered


def test_render_with_evidence():
    """Test rendering with actual evidence values."""
    candidate = create_reviewed_candidate()
    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id)}

    rendered = render_with_evidence(candidate, evidence, {})
    assert "Revenue was" in rendered
    # Should have the actual value from evidence
    assert "$100.00" in rendered or "100.00" in rendered


def test_render_with_chart():
    """Test rendering with chart artifacts."""
    candidate = create_reviewed_candidate()
    chart_id = CanonicalUUID("00000000-0000-1000-8000-000000000002")

    # Update candidate to include chart span
    draft = candidate.draft
    new_block = DraftBlock(
        block_id="b2",
        kind="data_claim",
        spans=[
            TextSpan(kind="text", text="Chart shows "),
            ChartSpan(kind="chart", chart_artifact_id=chart_id),
        ],
        supports=[
            ChartTarget(kind="chart", chart_artifact_id=chart_id),
        ],
    )
    new_draft = Draft(
        blocks=[draft.blocks[0], new_block],
        unmet_deliverables=[],
    )

    from copy import deepcopy
    new_candidate = deepcopy(candidate)
    new_candidate = ReviewedCandidate(
        candidate_id=new_candidate.candidate_id,
        scope=new_candidate.scope,
        content_hash=new_candidate.content_hash,
        rendered_text=new_candidate.rendered_text,
        rendering_policy_version=new_candidate.rendering_policy_version,
        dependencies=new_candidate.dependencies,
        source_input_hash=new_candidate.source_input_hash,
        valid_until=new_candidate.valid_until,
        originating_invocation_id=new_candidate.originating_invocation_id,
        kind="reviewed",
        draft_id=new_candidate.draft_id,
        draft=new_draft,
        completeness="complete",
        review=new_candidate.review,
        approval_ref=new_candidate.approval_ref,
    )

    charts = {str(chart_id): create_mock_chart(chart_id)}
    rendered = render_with_evidence(new_candidate, {}, charts)
    assert "Chart:" in rendered
    assert "Sales by Region" in rendered


def test_format_value():
    """Test value formatting."""
    assert _format_value(100, "exact") == "100"
    assert _format_value(100, "fixed_2") == "100.00"
    assert _format_value(0.5, "percent_1") == "50.0%"
    assert _format_value(1234.56, "currency_2") == "$1,234.56"
    assert _format_value("text", "iso") == "text"
    assert _format_value(None, "exact") == "[null]"

    # With unit
    assert _format_value(100, "fixed_2", "USD") == "100.00 USD"


def test_format_value_edge_cases():
    """Test formatting edge cases."""
    # Non-numeric values with numeric formats
    assert _format_value("not a number", "fixed_2") == "not a number"
    assert _format_value("not a number", "percent_1") == "not a number"
    assert _format_value("not a number", "currency_2") == "not a number"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])