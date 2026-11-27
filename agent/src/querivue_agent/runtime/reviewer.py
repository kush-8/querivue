"""Reviewer runtime for independent draft assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.evidence import TabularEvidence
from querivue_agent.contracts.content import DraftBlock, SupportTarget, BlockID
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.runtime.drafting import (
    TypedDraft,
    TypedDraftBlock,
    ReviewFinding,
    ReviewedAssessment,
    ReviewVerdict,
    DraftingEngine,
)


@dataclass(frozen=True)
class ReviewRequest:
    """Runtime review request."""
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    draft_content_hash: str
    draft_input_packet_hash: str
    rendering_policy_version: str
    review_pass: int
    original_question: str
    obligations: list[str] = field(default_factory=list)
    confirmed_context: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, TabularEvidence] = field(default_factory=dict)
    draft: TypedDraft = field(default_factory=lambda: None)  # Will be set
    unmet_deliverables_runtime: list[str] = field(default_factory=list)
    partial_authorized: bool = False
    partial_reason: str | None = None


@dataclass(frozen=True)
class ReviewState:
    """Reviewer internal state."""
    review_id: CanonicalUUID
    draft_id: CanonicalUUID
    review_pass: int
    messages: list[dict[str, Any]] = field(default_factory=list)
    findings: list[ReviewFinding] = field(default_factory=list)


class ReviewerEngine:
    """Engine for independent draft review."""

    def __init__(self) -> None:
        self._drafting_engine = DraftingEngine()

    def assess_draft(self, request: ReviewRequest) -> ReviewedAssessment:
        """
        Assess a draft independently against supplied evidence and context.
        This is the core review logic - in production this would call a model.
        """
        draft = request.draft
        findings = []

        # 1. Check all data claims have valid support
        for block in draft.blocks:
            if block.kind == "data_claim":
                findings.extend(self._check_data_claim(block, request))

        # 2. Check for unsupported causal claims
        findings.extend(self._check_causal_claims(draft, request))

        # 3. Check display formatting
        findings.extend(self._check_formatting(draft, request))

        # 4. Check unmet deliverables
        findings.extend(self._check_unmet_deliverables(draft, request))

        # 5. Check coverage and population claims
        findings.extend(self._check_coverage(draft, request))

        # 6. Check evidence sufficiency for partial authorization
        if draft.unmet_deliverables:
            findings.extend(self._check_partial_authorization(draft, request))

        # Determine verdict
        approved = len(findings) == 0

        return ReviewedAssessment(
            review_id=request.review_id,
            draft_id=request.draft_id,
            draft_content_hash=request.draft_content_hash,
            draft_input_packet_hash=request.draft_input_packet_hash,
            rendering_policy_version=request.rendering_policy_version,
            review_pass=request.review_pass,
            approved=approved,
            findings=findings,
        )

    def _check_data_claim(
        self,
        block: TypedDraftBlock,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check that data claims have valid support."""
        findings = []

        for span in block.spans:
            if hasattr(span, 'target') and isinstance(span.target, dict):
                target_type = span.target.get("type")
                if target_type == "cell":
                    evidence_id = span.target.get("evidence_id")
                    if evidence_id not in request.evidence:
                        findings.append(ReviewFinding(
                            finding_id=BlockID(f"F{len(findings)+1}"),
                            category="evidence",
                            affected_block_ids=[block.block_id],
                            explanation=f"Value span references evidence {evidence_id} which is not in the supplied packet",
                            support_refs=[],
                            required_change=f"Provide evidence {evidence_id} or remove unsupported claim",
                        ))

        return findings

    def _check_causal_claims(
        self,
        draft: TypedDraft,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check for unsupported causal assertions."""
        findings = []

        causal_keywords = ["because", "caused by", "due to", "resulted in", "led to", "driven by"]

        for block in draft.blocks:
            for span in block.spans:
                if isinstance(span, str):
                    text_lower = span.lower()
                    for keyword in causal_keywords:
                        if keyword in text_lower:
                            # Check if there's evidence supporting the causal claim
                            has_evidence_support = False
                            for support in block.supports:
                                if isinstance(support, dict) and support.get("type") in ("cell", "coverage"):
                                    has_evidence_support = True
                                    break

                            if not has_evidence_support:
                                findings.append(ReviewFinding(
                                    finding_id=BlockID(f"F{len(findings)+1}"),
                                    category="draft",
                                    affected_block_ids=[block.block_id],
                                    explanation=f"Causal claim detected ('{keyword}') without supporting evidence in block",
                                    support_refs=[],
                                    required_change="Remove causal assertion or provide computed attribution evidence",
                                ))

        return findings

    def _check_formatting(
        self,
        draft: TypedDraft,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check value formatting matches evidence."""
        findings = []

        # This would check actual rendered values against evidence values
        # For now, basic validation

        for block in draft.blocks:
            for span in block.spans:
                if hasattr(span, 'format') and hasattr(span, 'value'):
                    # Could validate format compatibility with value type
                    pass

        return findings

    def _check_unmet_deliverables(
        self,
        draft: TypedDraft,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check that unmet deliverables match runtime facts."""
        findings = []

        # Check if draft declares completeness but has unmet deliverables
        for ud in draft.unmet_deliverables:
            # Check if this matches runtime-recorded unmet deliverables
            if ud.description not in request.unmet_deliverables_runtime:
                findings.append(ReviewFinding(
                    finding_id=BlockID(f"F{len(findings)+1}"),
                    category="draft",
                    affected_block_ids=[],
                    explanation=f"Draft declares unmet deliverable '{ud.description}' not recorded by runtime",
                    support_refs=[],
                    required_change="Align unmet deliverables with runtime facts or request authorization",
                ))

        # Check if runtime has unmet deliverables not in draft
        for runtime_ud in request.unmet_deliverables_runtime:
            if not any(ud.description == runtime_ud for ud in draft.unmet_deliverables):
                findings.append(ReviewFinding(
                    finding_id=BlockID(f"F{len(findings)+1}"),
                    category="draft",
                    affected_block_ids=[],
                    explanation=f"Runtime records unmet deliverable '{runtime_ud}' missing from draft",
                    support_refs=[],
                    required_change="Add missing unmet deliverable to draft or explain why not needed",
                ))

        return findings

    def _check_coverage(
        self,
        draft: TypedDraft,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check that coverage claims match evidence visibility."""
        findings = []

        for block in draft.blocks:
            if block.kind == "data_claim":
                for support in block.supports:
                    if isinstance(support, dict) and support.get("type") == "coverage":
                        evidence_id = support.get("evidence_id")
                        if evidence_id in request.evidence:
                            ev = request.evidence[evidence_id]
                            if ev.row_count > 1000:  # Arbitrary threshold for "large" results
                                # Check if draft makes population-level claim from preview
                                pass  # Would need semantic analysis

        return findings

    def _check_partial_authorization(
        self,
        draft: TypedDraft,
        request: ReviewRequest,
    ) -> list[ReviewFinding]:
        """Check partial drafts have proper authorization."""
        findings = []

        if draft.unmet_deliverables and not request.partial_authorized:
            findings.append(ReviewFinding(
                finding_id=BlockID(f"F{len(findings)+1}"),
                category="draft",
                affected_block_ids=[],
                explanation="Draft declares unmet deliverables but no partial authorization was granted",
                support_refs=[],
                required_change="Obtain partial authorization from supervisor or remove unmet items",
            ))

        return findings


def create_reviewer_engine() -> ReviewerEngine:
    """Create a reviewer engine instance."""
    return ReviewerEngine()