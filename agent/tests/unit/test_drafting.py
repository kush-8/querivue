"""Unit tests for typed drafting and review."""

from __future__ import annotations

from uuid import uuid4

import pytest

from querivue_agent.contracts.evidence import TabularEvidence
from querivue_agent.contracts.artifacts import ArtifactRef
from querivue_agent.contracts.content import DraftBlock, SupportTarget
from querivue_agent.contracts.values import CanonicalUUID, Int64Scalar
from querivue_agent.contracts.content import BlockID
from querivue_agent.runtime.drafting import (
    TypedDraft,
    TypedDraftBlock,
    UnmetDeliverable,
    ValueSpan,
    ChartSpan,
    DraftReady,
    Blocked,
    Failed,
    DraftingEngine,
    create_value_span,
    create_chart_span,
    create_block,
    DisplayFormat,
    ContentSpan,
)
from querivue_agent.runtime.reviewer import (
    ReviewRequest,
    ReviewerEngine,
    ReviewFinding,
    ReviewedAssessment,
)
from querivue_agent.runtime.drafting import create_value_span, create_chart_span, create_block


def create_mock_evidence(evidence_id: CanonicalUUID, row_count: int = 10) -> TabularEvidence:
    """Create mock tabular evidence for testing."""
    from querivue_agent.contracts.artifacts import ArtifactRef
    from querivue_agent.contracts.evidence import (
        EvidenceColumn, TabularPreview, Producer, SourceDependency,
        Int64Column, StringColumn, CellLocator, SQLProducer,
    )
    from querivue_agent.contracts.common import SafeCount, PositiveCount
    from querivue_agent.contracts.actions import AnalysisConstraints
    from querivue_agent.contracts.values import Int64Scalar

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
            rows=[],
            row_locators=[],
            full_row_count=row_count,
            returned_row_count=SafeCount(0),
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


def test_create_value_span():
    """Test creating a value span."""
    span = create_value_span(
        evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
        row_locator=0,
        column_ordinal=0,
        value=42,
        format="fixed_2",
        unit="USD",
    )
    assert span.value == 42
    assert span.format == "fixed_2"
    assert span.unit == "USD"
    assert span.target["type"] == "cell"
    assert span.target["row_locator"] == 0


def test_create_chart_span():
    """Test creating a chart span."""
    span = create_chart_span(
        chart_artifact_id=CanonicalUUID("00000000-0000-1000-8000-000000000002"),
        caption="Sales by region",
    )
    assert span.chart_artifact_id == CanonicalUUID("00000000-0000-1000-8000-000000000002")
    assert span.caption == "Sales by region"


def test_create_block():
    """Test creating a typed draft block."""
    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=["Revenue was ", create_value_span(
            evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": "00000000-0000-1000-8000-000000000001", "row_locator": 0, "column_ordinal": 0}],
    )
    assert block.block_id == BlockID("b1")
    assert block.kind == "data_claim"
    assert len(block.spans) == 2


def test_typed_draft_creation():
    """Test creating a complete typed draft."""
    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": "00000000-0000-1000-8000-000000000001", "row_locator": 0, "column_ordinal": 0}],
    )

    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
        unmet_deliverables=[],
    )
    assert len(draft.blocks) == 1
    assert draft.blocks[0].block_id == BlockID("b1")


def test_typed_draft_duplicate_block_ids():
    """Test that duplicate block IDs are rejected."""
    block1 = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=["test"],
        supports=[],
    )
    block2 = create_block(
        block_id=BlockID("b1"),  # Duplicate
        kind="general_explanation",
        spans=["test"],
        supports=[],
    )

    with pytest.raises(ValueError, match="block_id values must be unique"):
        TypedDraft(
            draft_id=CanonicalUUID(str(uuid4())),
            blocks=[block1, block2],
        )


def test_drafting_engine_validation():
    """Test draft validation against evidence."""
    engine = DraftingEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    # Valid draft
    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    errors = engine.validate_draft(draft, evidence)
    assert len(errors) == 0

    # Invalid evidence reference
    block2 = create_block(
        block_id=BlockID("b2"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=CanonicalUUID("00000000-0000-1000-8000-000000000002"),
            row_locator=0,
            column_ordinal=0,
            value=200,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": "00000000-0000-1000-8000-000000000002", "row_locator": 0, "column_ordinal": 0}],
    )
    draft2 = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block2],
    )
    errors2 = engine.validate_draft(draft2, evidence)
    assert len(errors2) > 0
    assert "not found" in errors2[0]


def test_draft_rendering():
    """Test rendering a draft to text."""
    engine = DraftingEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=["Revenue: ", create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="currency_2",
        )],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    rendered = engine.render_draft(draft, evidence)
    assert "Revenue:" in rendered
    assert "$100.00" in rendered


def test_reviewer_engine_basic():
    """Test basic reviewer engine operation."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    request = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="What is the revenue?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is True
    assert len(assessment.findings) == 0


def test_reviewer_catches_unsupported_causal_claim():
    """Test that reviewer catches causal claims without evidence."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=["Revenue increased because of the marketing campaign."],
        supports=[],  # No evidence support for causal claim
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    request = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="Why did revenue increase?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is False
    assert len(assessment.findings) > 0
    assert any(f.category == "draft" for f in assessment.findings)
    assert any("causal" in f.explanation.lower() for f in assessment.findings)


def test_reviewer_catches_missing_evidence():
    """Test that reviewer catches missing evidence references."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    # Draft references evidence that doesn't exist
    missing_id = CanonicalUUID("00000000-0000-1000-8000-000000000002")
    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=missing_id,
            row_locator=0,
            column_ordinal=0,
            value=200,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": str(missing_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    request = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="What is the value?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is False
    assert len(assessment.findings) > 0
    assert any(f.category == "evidence" for f in assessment.findings)


def test_reviewer_checks_unmet_deliverables():
    """Test that reviewer checks unmet deliverables against runtime."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {
        str(evidence_id): create_mock_evidence(evidence_id, row_count=100)
    }

    block = create_block(
        block_id=BlockID("b1"),
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=100,
            format="exact",
        )],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
        unmet_deliverables=[
            UnmetDeliverable(
                description="Missing chart",
                reason="Chart generation failed",
                required_evidence="Chart artifact",
            )
        ],
    )

    request = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="Show revenue with chart",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=["Missing chart"],  # Runtime records same
        partial_authorized=True,
    )

    assessment = engine.assess_draft(request)
    # Should be approved since unmet matches runtime
    assert assessment.approved is True


def test_draft_ready_blocked_failed():
    """Test draft outcome variants."""
    # DraftReady
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[create_block(
            block_id=BlockID("b1"),
            kind="data_claim",
            spans=["test"],
            supports=[],
        )],
    )
    ready = DraftReady(draft=draft, completeness="complete")
    assert ready.completeness == "complete"

    # Blocked
    blocked = Blocked(
        explanation="Missing evidence",
        requirements=[{"kind": "evidence", "description": "Need revenue data"}],
    )
    assert len(blocked.requirements) == 1

    # Failed
    failed = Failed(error_ref="err_123", stage="drafting")
    assert failed.stage == "drafting"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])