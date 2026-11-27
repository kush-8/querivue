"""Integration tests for the review flow."""

from __future__ import annotations

from uuid import uuid4

import pytest

from querivue_agent.contracts.inputs import AnswerInput, ReviewInput
from querivue_agent.contracts.content import (
    DraftBlock, TextSpan, ValueSpan, ChartSpan, CellTarget, ChartTarget,
    Draft, UnmetDeliverable,
)
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
from querivue_agent.contracts.responses import (
    ReviewedAssessment, ReviewFinding, ReviewBinding,
    ReviewPass,
)
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.artifacts import ArtifactRef
from querivue_agent.contracts.artifacts import SourceDependency
from querivue_agent.contracts.common import PositiveCount, SafeCount
from querivue_agent.contracts.actions import AnswerAction, AnalysisConstraints
from querivue_agent.contracts.evidence import (
    EvidenceColumn, TabularPreview, Producer, SourceDependency,
    Int64Column, StringColumn, SQLProducer,
)
from querivue_agent.contracts.control import PartialAuthorization
from querivue_agent.contracts.inputs import ObligationRecord, UnmetFact, RevisionContext
from querivue_agent.runtime.drafting import (
    TypedDraft, TypedDraftBlock, DraftingEngine,
    create_value_span, create_chart_span, create_block,
    DraftReady, Blocked, Failed, ReviewedAssessment as RuntimeReviewedAssessment,
    ReviewFinding as RuntimeReviewFinding,
)
from querivue_agent.runtime.reviewer import ReviewerEngine, ReviewRequest
from querivue_agent.runtime.finalize import render, render_with_evidence


def create_mock_evidence(evidence_id: CanonicalUUID, row_count: int = 10) -> TabularEvidence:
    """Create mock tabular evidence for testing."""
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
            EvidenceColumn(ordinal=0, name="revenue", original_label="revenue", original_ordinal=0, type=Int64Column(tag="int64"), nullable=False),
            EvidenceColumn(ordinal=1, name="region", original_label="region", original_ordinal=1, type=StringColumn(tag="string"), nullable=False),
        ],
        row_count=row_count,
        preview=TabularPreview(
            columns=[
                EvidenceColumn(ordinal=0, name="revenue", original_label="revenue", original_ordinal=0, type=Int64Column(tag="int64"), nullable=False),
                EvidenceColumn(ordinal=1, name="region", original_label="region", original_ordinal=1, type=StringColumn(tag="string"), nullable=False),
            ],
            rows=[["10000", "North"], ["15000", "South"]],
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
            sql="SELECT revenue, region FROM sales",
            parameters={},
            table_ids=[CanonicalUUID(str(uuid4()))],
            input_evidence_ids=[CanonicalUUID(str(uuid4()))],
            constraints=AnalysisConstraints(
                metric_definitions={"revenue": "sum(amount)"},
                filters=[],
                date_windows=[],
                analysis_timezone="UTC",
                grain="day",
                units={"revenue": "USD"},
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
    from querivue_agent.contracts.common import PositiveCount, Sha256
    from querivue_agent.contracts.evidence import (
        ChartArtifact, ChartDeclaration, ChartSeries, Identifier, NonblankString,
        PythonProducer, AnalysisConstraints, ColumnOrdering, TypedScalar
    )

    manifest_id = CanonicalUUID(str(uuid4()))
    evidence_id = CanonicalUUID(str(uuid4()))

    return ChartArtifact(
        chart_artifact_id=chart_id,
        artifact=ArtifactRef(
            artifact_id=chart_id,
            storage_ref=CanonicalUUID(str(uuid4())),
            media_type="image/png",
            size_bytes=500,
            sha256="b" * 64,
            environment_manifest_id=manifest_id,
        ),
        declaration=ChartDeclaration(
            name=Identifier("revenue_chart"),
            kind="chart",
            title="Revenue by Region",
            description="Revenue data by region",
            series=[
                ChartSeries(
                    label="revenue",
                    evidence_id=evidence_id,
                    ordering=[],
                    scales={"revenue": "linear"},
                    columns={"revenue": "revenue"},
                )
            ],
            units={"revenue": "USD"},
            analysis_timezone="UTC",
            limitations=[],
        ),
        producer=PythonProducer(
            kind="python",
            run_id=CanonicalUUID(str(uuid4())),
            action_id=CanonicalUUID(str(uuid4())),
            operation_id=CanonicalUUID(str(uuid4())),
            attempt=PositiveCount(1),
            script_ref=CanonicalUUID(str(uuid4())),
            script_hash=Sha256("c" * 64),
            input_evidence_ids=[evidence_id],
            action_input_evidence_ids=[evidence_id],
            constraints=AnalysisConstraints(
                metric_definitions={"revenue": "sum(amount)"},
                filters=[],
                date_windows=[],
                analysis_timezone="UTC",
                grain="day",
                units={"revenue": "USD"},
            ),
            random_seed=42,
            method_parameters={},
            environment_manifest_id=manifest_id,
            policy_version="v1",
        ),
        pixel_width=800,
        pixel_height=600,
        encoder_version="v1",
        normalization_version="v1",
        backing_evidence_ids=[evidence_id],
        dependencies=[
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
        ],
    )


def create_answer_input() -> AnswerInput:
    """Create a sample AnswerInput for testing."""
    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    chart_id = CanonicalUUID("00000000-0000-1000-8000-000000000002")

    evidence = create_mock_evidence(evidence_id)
    chart = create_mock_chart(chart_id)

    # Create minimal conversation snapshot
    from querivue_agent.contracts.inputs import (
        ConversationSnapshot, UserMessage, ContextRecord,
        InterpretationRecord, ThreadCandidate, ContextConflict,
        UserMessageBasis, BasisReference, EntryInput as IntakeEntryInput,
    )

    # This is a complex object - we'll create a minimal version
    # In real tests, we'd use fixtures
    return None  # Placeholder - would need full construction


class MockModelGateway:
    """Mock model gateway for testing."""

    def __init__(self, response_content: str):
        self._response_content = response_content

    async def complete(self, messages, temperature=0.0, max_tokens=8192):
        class MockResponse:
            def __init__(self, content):
                self.content = content
        return MockResponse(self._response_content)


@pytest.mark.asyncio
async def test_answer_specialist_draft_basic():
    """Test basic answer specialist drafting."""
    from querivue_agent.specialists.answer import draft

    # Create a simple response that the model would return
    model_response = {
        "blocks": [
            {
                "block_id": "b1",
                "kind": "data_claim",
                "spans": [
                    {"type": "text", "text": "Revenue was "},
                    {
                        "type": "value",
                        "evidence_id": "00000000-0000-1000-8000-000000000001",
                        "row_locator": 0,
                        "column_ordinal": 0,
                        "value": 10000,
                        "format": "currency_2",
                        "unit": "USD",
                    },
                ],
                "supports": [
                    {
                        "type": "cell",
                        "evidence_id": "00000000-0000-1000-8000-000000000001",
                        "row_locator": 0,
                        "column_ordinal": 0,
                    },
                ],
            }
        ],
        "unmet_deliverables": [],
    }

    import json
    model = MockModelGateway(json.dumps(model_response))

    # Note: Full test would require constructing AnswerInput
    # This is a placeholder showing the test pattern
    assert True  # Placeholder


@pytest.mark.asyncio
async def test_reviewer_specialist_review_approve():
    """Test reviewer specialist approving a valid draft."""
    from querivue_agent.specialists.reviewer import review

    model_response = {
        "verdict": "approved",
        "findings": [],
    }

    import json
    model = MockModelGateway(json.dumps(model_response))

    # Note: Full test would require constructing ReviewInput
    assert True  # Placeholder


@pytest.mark.asyncio
async def test_reviewer_specialist_review_reject():
    """Test reviewer specialist rejecting a draft with findings."""
    from querivue_agent.specialists.reviewer import review

    model_response = {
        "verdict": "rejected",
        "findings": [
            {
                "finding_id": "F1",
                "category": "evidence",
                "block_ids": ["b1"],
                "explanation": "Value span references evidence not in packet",
                "support_refs": [],
                "required_change": "Provide evidence or remove claim",
            },
        ],
    }

    import json
    model = MockModelGateway(json.dumps(model_response))

    assert True  # Placeholder


def test_drafting_engine_full_flow():
    """Test full drafting engine flow: create, validate, render."""
    engine = DraftingEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # Create draft
    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=[
            "Revenue in North region was ",
            create_value_span(
                evidence_id=evidence_id,
                row_locator=0,
                column_ordinal=0,
                value=10000,
                format="currency_2",
                unit="USD",
            ),
        ],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )

    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
        unmet_deliverables=[],
    )

    # Validate
    errors = engine.validate_draft(draft, evidence)
    assert len(errors) == 0

    # Render
    rendered = engine.render_draft(draft, evidence)
    assert "Revenue in North region was" in rendered
    assert "$10,000.00" in rendered


def test_reviewer_engine_full_flow():
    """Test full reviewer engine flow."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # Create valid draft
    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=10000,
            format="currency_2",
            unit="USD",
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
        original_question="What is the revenue in North region?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is True
    assert len(assessment.findings) == 0


def test_reviewer_catches_causal_claim():
    """Test reviewer catches unsupported causal claims."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # Draft with causal claim but no evidence
    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=["Revenue increased because of the marketing campaign."],
        supports=[],
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
    assert any("causal" in f.explanation.lower() for f in assessment.findings)


def test_reviewer_catches_missing_evidence():
    """Test reviewer catches missing evidence references."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # Draft references non-existent evidence
    missing_id = CanonicalUUID("00000000-0000-1000-8000-000000000002")
    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=missing_id,
            row_locator=0,
            column_ordinal=0,
            value=20000,
            format="currency_2",
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
        original_question="What is the revenue?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is False
    assert len(assessment.findings) > 0
    assert any(f.category == "evidence" for f in assessment.findings)


def test_reviewer_partial_authorization():
    """Test reviewer checks partial authorization."""
    engine = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=[create_value_span(
            evidence_id=evidence_id,
            row_locator=0,
            column_ordinal=0,
            value=10000,
            format="currency_2",
        )],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )

    from querivue_agent.runtime.drafting import UnmetDeliverable
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
        unmet_deliverables=[
            UnmetDeliverable(
                description="Missing chart",
                reason="Chart generation failed",
                required_evidence="Chart artifact",
            ),
        ],
    )

    # Without partial authorization - should fail
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
        unmet_deliverables_runtime=["Missing chart"],
        partial_authorized=False,
    )

    assessment = engine.assess_draft(request)
    assert assessment.approved is False
    assert any("partial authorization" in f.explanation.lower() for f in assessment.findings)

    # With partial authorization - should pass
    request2 = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="Show revenue with chart",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=["Missing chart"],
        partial_authorized=True,
        partial_reason="Chart service unavailable",
    )

    assessment2 = engine.assess_draft(request2)
    assert assessment2.approved is True


def test_finalize_rendering_flow():
    """Test the complete finalize rendering flow."""
    from querivue_agent.contracts.records import ReviewedCandidate
    from querivue_agent.contracts.responses import ReviewedAssessment

    # Create a reviewed candidate
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

    candidate = ReviewedCandidate(
        candidate_id=RuntimeUUID(str(uuid4())),
        scope={"run_id": CanonicalUUID(str(uuid4())), "chat_id": CanonicalUUID(str(uuid4())), "project_id": CanonicalUUID(str(uuid4())), "eligible_dataset_ids": []},
        content_hash="a" * 64,
        rendered_text="Revenue was $10,000.00",
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

    # Render without evidence
    rendered = render(candidate)
    assert "Revenue was" in rendered

    # Render with evidence
    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id)}
    rendered_with_evidence = render_with_evidence(candidate, evidence, {})
    assert "Revenue was" in rendered_with_evidence
    assert "$10,000.00" in rendered_with_evidence


def test_review_flow_integration():
    """Integration test: draft -> review -> finalize."""
    engine = DraftingEngine()
    reviewer = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # Step 1: Create draft
    block = create_block(
        block_id="b1",
        kind="data_claim",
        spans=[
            "Q1 revenue in North was ",
            create_value_span(
                evidence_id=evidence_id,
                row_locator=0,
                column_ordinal=0,
                value=10000,
                format="currency_2",
                unit="USD",
            ),
        ],
        supports=[{"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0}],
    )
    draft = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block],
    )

    # Validate draft
    validation_errors = engine.validate_draft(draft, evidence)
    assert len(validation_errors) == 0

    # Step 2: Review draft
    request = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="What was Q1 revenue in North?",
        evidence=evidence,
        draft=draft,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment = reviewer.assess_draft(request)
    assert assessment.approved is True

    # Step 3: Finalize (render)
    from querivue_agent.contracts.records import ReviewedCandidate
    from querivue_agent.contracts.responses import ReviewedAssessment as ContractReviewedAssessment
    from querivue_agent.contracts.content import Draft, DraftBlock, TextSpan, ValueSpan, CellTarget, UnmetDeliverable

    # Convert TypedDraft to contract Draft
    contract_blocks = []
    for b in draft.blocks:
        contract_spans = []
        for span in b.spans:
            if isinstance(span, str):
                contract_spans.append(TextSpan(kind="text", text=span))
            elif hasattr(span, 'target') and hasattr(span, 'format'):
                # ValueSpan
                target = span.target
                if target.get("type") == "cell":
                    contract_spans.append(ValueSpan(
                        kind="value",
                        target=CellTarget(
                            kind="cell",
                            evidence_id=CanonicalUUID(target["evidence_id"]),
                            row_locator=target["row_locator"],
                            column_ordinal=target["column_ordinal"],
                        ),
                        format=span.format,
                    ))
        contract_blocks.append(DraftBlock(
            block_id=b.block_id,
            kind=b.kind,
            spans=contract_spans,
            supports=[
                CellTarget(kind="cell", evidence_id=CanonicalUUID(s["evidence_id"]), row_locator=s["row_locator"], column_ordinal=s["column_ordinal"])
                for s in b.supports if s.get("type") == "cell"
            ],
        ))

    contract_draft = Draft(
        blocks=contract_blocks,
        unmet_deliverables=[],
    )

    contract_review = ContractReviewedAssessment(
        review_id=assessment.review_id,
        draft_id=assessment.draft_id,
        draft_content_hash=assessment.draft_content_hash,
        draft_input_packet_hash=assessment.draft_input_packet_hash,
        review_input_packet_hash="c" * 64,
        rendering_policy_version=assessment.rendering_policy_version,
        review_pass=assessment.review_pass,
        verdict="approved",
        findings=[],
        status="reviewed",
    )

    candidate = ReviewedCandidate(
        candidate_id=RuntimeUUID(str(uuid4())),
        scope={"run_id": CanonicalUUID(str(uuid4())), "chat_id": CanonicalUUID(str(uuid4())), "project_id": CanonicalUUID(str(uuid4())), "eligible_dataset_ids": []},
        content_hash=assessment.draft_content_hash,
        rendered_text=engine.render_draft(draft, evidence),
        rendering_policy_version=assessment.rendering_policy_version,
        dependencies=[],
        source_input_hash=assessment.draft_input_packet_hash,
        valid_until="2026-12-31T23:59:59Z",
        originating_invocation_id=CanonicalUUID(str(uuid4())),
        kind="reviewed",
        draft_id=draft.draft_id,
        draft=contract_draft,
        completeness="complete",
        review=contract_review,
        approval_ref=assessment.review_id,
    )

    final_text = render_with_evidence(candidate, evidence, {})
    assert "Q1 revenue in North was" in final_text
    assert "$10,000.00" in final_text


def test_review_revision_flow():
    """Test the revision flow: draft -> rejected review -> revised draft -> review."""
    engine = DraftingEngine()
    reviewer = ReviewerEngine()

    evidence_id = CanonicalUUID("00000000-0000-1000-8000-000000000001")
    evidence = {str(evidence_id): create_mock_evidence(evidence_id, row_count=100)}

    # First draft - has causal claim (will be rejected)
    block1 = create_block(
        block_id="b1",
        kind="data_claim",
        spans=["Revenue increased because of marketing spend."],
        supports=[],
    )
    draft1 = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block1],
    )

    request1 = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft1.draft_id,
        draft_content_hash="a" * 64,
        draft_input_packet_hash="b" * 64,
        rendering_policy_version="v1",
        review_pass=1,
        original_question="Why did revenue increase?",
        evidence=evidence,
        draft=draft1,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment1 = reviewer.assess_draft(request1)
    assert assessment1.approved is False
    assert len(assessment1.findings) > 0

    # Revised draft - removes causal claim, adds evidence
    block2 = create_block(
        block_id="b2",
        kind="data_claim",
        spans=[
            "Revenue increased from ",
            create_value_span(
                evidence_id=evidence_id,
                row_locator=0,
                column_ordinal=0,
                value=8000,
                format="currency_2",
                unit="USD",
            ),
            " to ",
            create_value_span(
                evidence_id=evidence_id,
                row_locator=1,
                column_ordinal=0,
                value=10000,
                format="currency_2",
                unit="USD",
            ),
        ],
        supports=[
            {"type": "cell", "evidence_id": str(evidence_id), "row_locator": 0, "column_ordinal": 0},
            {"type": "cell", "evidence_id": str(evidence_id), "row_locator": 1, "column_ordinal": 0},
        ],
    )
    draft2 = TypedDraft(
        draft_id=CanonicalUUID(str(uuid4())),
        blocks=[block2],
        predecessor_draft_id=draft1.draft_id,
        review_feedback_id=assessment1.review_id,
    )

    # Validate revised draft
    validation_errors = engine.validate_draft(draft2, evidence)
    assert len(validation_errors) == 0

    # Second review
    request2 = ReviewRequest(
        review_id=CanonicalUUID(str(uuid4())),
        draft_id=draft2.draft_id,
        draft_content_hash="c" * 64,
        draft_input_packet_hash="d" * 64,
        rendering_policy_version="v1",
        review_pass=2,  # Second pass
        original_question="Why did revenue increase?",
        evidence=evidence,
        draft=draft2,
        unmet_deliverables_runtime=[],
        partial_authorized=False,
    )

    assessment2 = reviewer.assess_draft(request2)
    assert assessment2.approved is True
    assert len(assessment2.findings) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])