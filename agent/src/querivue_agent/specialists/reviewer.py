"""Reviewer Specialist implementation."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from querivue_agent.contracts.inputs import ReviewInput
from querivue_agent.contracts.responses import ReviewAssessment
from querivue_agent.runtime.reviewer import ReviewerEngine, ReviewRequest
from querivue_agent.runtime.prompts import load_prompt
from querivue_agent.runtime.wrappers import WrapperContext

if __name__:
    from querivue_agent.providers.base import ModelGateway


async def review(
    request: ReviewInput,
    *,
    model: ModelGateway,
) -> ReviewAssessment:
    """Review a draft independently using the reviewer prompt."""
    # Build the prompt
    prompt_template = load_prompt("reviewer")

    # Prepare the draft for review - rendered text is already provided
    draft_text = request.rendered_text

    # Prepare evidence summary
    evidence_summaries = []
    for ev in request.draft_input.evidence:
        evidence_summaries.append(
            f"Evidence {ev.evidence_id}: {ev.row_count} rows, "
            f"columns: {[c.name for c in ev.columns]}"
        )

    # Prepare obligations
    obligations = []
    for obl in request.draft_input.obligations:
        obligations.append(f"Obligation {obl.obligation_ref}: {obl.description} ({obl.state})")

    # Prepare unmet facts
    unmet_facts = []
    for gap in request.draft_input.unmet_facts:
        unmet_facts.append(
            f"Gap {gap.gap_ref}: {gap.description} (status: {gap.status})"
        )

    # Prepare partial authorization if present
    partial_auth = ""
    if request.draft_input.partial_authorization:
        pa = request.draft_input.partial_authorization
        partial_auth = (
            f"Partial Authorization: gaps={pa.gap_refs}, "
            f"obligations={pa.unmet_obligation_refs}, "
            f"supporting={pa.supporting_refs}, reason={pa.reason}"
        )

    # Build review packet hash
    import hashlib
    packet_data = {
        "review_id": str(request.request.review_id),
        "draft_id": str(request.request.draft_id),
        "draft_content_hash": request.request.draft_content_hash,
        "draft_input_packet_hash": request.request.draft_input_packet_hash,
        "rendering_policy_version": request.request.rendering_policy_version,
        "review_pass": request.request.review_pass,
    }
    packet_hash = hashlib.sha256(json.dumps(packet_data, sort_keys=True).encode()).hexdigest()

    # Format prompt
    formatted_prompt = prompt_template.format(
        original_question=request.draft_input.conversation.original_message.text,
        rendered_draft=draft_text,
        evidence_summary="\n".join(evidence_summaries) if evidence_summaries else "No evidence",
        obligations="\n".join(obligations) if obligations else "No obligations",
        unmet_facts="\n".join(unmet_facts) if unmet_facts else "No unmet facts",
        partial_authorization=partial_auth if partial_auth else "None granted",
        review_pass=request.request.review_pass,
        rendering_policy_version=request.request.rendering_policy_version,
        packet_hash=packet_hash,
    )

    # Call model
    response = await model.complete(
        messages=[{"role": "user", "content": formatted_prompt}],
        temperature=0.0,
        max_tokens=8192,
    )

    # Parse response - expect JSON with findings
    try:
        content = response.content
        parsed = json.loads(content)

        verdict = parsed.get("verdict", "rejected")
        findings = []

        for finding_data in parsed.get("findings", []):
            finding_id = finding_data.get("finding_id", f"F{len(findings)+1}")
            findings.append({
                "finding_id": finding_id,
                "category": finding_data.get("category", "draft"),
                "block_ids": finding_data.get("block_ids", []),
                "explanation": finding_data.get("explanation", ""),
                "support_refs": finding_data.get("support_refs", []),
                "required_change": finding_data.get("required_change", ""),
            })

        # Build assessment
        if verdict == "approved" and not findings:
            return ReviewAssessment(
                review_id=request.request.review_id,
                draft_id=request.request.draft_id,
                draft_content_hash=request.request.draft_content_hash,
                draft_input_packet_hash=request.request.draft_input_packet_hash,
                review_input_packet_hash=request.packet.content_hash,
                rendering_policy_version=request.request.rendering_policy_version,
                review_pass=request.request.review_pass,
                verdict="approved",
                findings=[],
                status="reviewed",
            )
        else:
            # Ensure we have at least one finding if rejected
            if not findings:
                findings.append({
                    "finding_id": "F1",
                    "category": "draft",
                    "block_ids": [],
                    "explanation": "Model returned rejection without specific findings",
                    "support_refs": [],
                    "required_change": "Provide specific blocking findings for rejection",
                })

            return ReviewAssessment(
                review_id=request.request.review_id,
                draft_id=request.request.draft_id,
                draft_content_hash=request.request.draft_content_hash,
                draft_input_packet_hash=request.request.draft_input_packet_hash,
                review_input_packet_hash=request.packet.content_hash,
                rendering_policy_version=request.request.rendering_policy_version,
                review_pass=request.request.review_pass,
                verdict="rejected",
                findings=findings,
                status="reviewed",
            )

    except json.JSONDecodeError:
        # Failed review
        return ReviewAssessment(
            review_id=request.request.review_id,
            draft_id=request.request.draft_id,
            draft_content_hash=request.request.draft_content_hash,
            draft_input_packet_hash=request.request.draft_input_packet_hash,
            review_input_packet_hash=request.packet.content_hash,
            rendering_policy_version=request.request.rendering_policy_version,
            review_pass=request.request.review_pass,
            verdict="rejected",
            findings=[{
                "finding_id": "F1",
                "category": "draft",
                "block_ids": [],
                "explanation": "Reviewer produced invalid JSON output",
                "support_refs": [],
                "required_change": "Fix reviewer output format",
            }],
            status="reviewed",
        )
    except Exception as e:
        # Failed review
        return ReviewAssessment(
            review_id=request.request.review_id,
            draft_id=request.request.draft_id,
            draft_content_hash=request.request.draft_content_hash,
            draft_input_packet_hash=request.request.draft_input_packet_hash,
            review_input_packet_hash=request.packet.content_hash,
            rendering_policy_version=request.request.rendering_policy_version,
            review_pass=request.request.review_pass,
            verdict="rejected",
            findings=[{
                "finding_id": "F1",
                "category": "draft",
                "block_ids": [],
                "explanation": f"Reviewer error: {type(e).__name__}",
                "support_refs": [],
                "required_change": "Fix reviewer runtime error",
            }],
            status="reviewed",
        )


class ReviewerSpecialist:
    """Reviewer specialist for independent draft assessment."""

    def __init__(self, context: WrapperContext) -> None:
        self._context = context
        self._engine = ReviewerEngine()

    async def review(self, request: ReviewInput, model: ModelGateway) -> ReviewAssessment:
        """Execute the review workflow."""
        return await review(request, model=model)