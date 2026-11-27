"""Answer Specialist implementation."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING
from uuid import UUID

from querivue_agent.contracts.inputs import AnswerInput, AnswerOutcome
from querivue_agent.contracts.content import DraftBlock
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.runtime.drafting import (
    DraftingEngine,
    TypedDraft,
    create_block,
    create_value_span,
    create_chart_span,
    DraftReady,
    Blocked,
    Failed,
)
from querivue_agent.runtime.prompts import load_prompt
from querivue_agent.runtime.wrappers import WrapperContext

if TYPE_CHECKING:
    from querivue_agent.providers.base import ModelGateway


async def draft(
    request: AnswerInput,
    *,
    model: ModelGateway,
) -> AnswerOutcome:
    """Draft an evidence-grounded answer using the answer specialist prompt."""
    # Build the prompt
    prompt_template = load_prompt("answer_specialist")

    # Prepare evidence summary for the prompt
    evidence_summaries = []
    for ev_id in request.evidence_ids:
        # In real implementation, we'd fetch evidence from storage
        evidence_summaries.append(f"Evidence {ev_id}: [would fetch from ledger]")

    # Prepare chart artifact references
    chart_refs = [str(c) for c in request.chart_artifact_ids]

    # Build the input packet hash (simplified)
    import hashlib
    packet_data = {
        "question": request.question,
        "evidence_ids": [str(e) for e in request.evidence_ids],
        "chart_artifact_ids": chart_refs,
        "deliverables": request.deliverables,
        "rendering_policy_version": request.rendering_policy_version,
    }
    packet_hash = hashlib.sha256(json.dumps(packet_data, sort_keys=True).encode()).hexdigest()

    # Format prompt
    formatted_prompt = prompt_template.format(
        question=request.question,
        evidence_summary="\n".join(evidence_summaries) if evidence_summaries else "No evidence provided",
        chart_artifacts="\n".join(chart_refs) if chart_refs else "No chart artifacts",
        deliverables=request.deliverables,
        rendering_policy_version=request.rendering_policy_version,
        packet_hash=packet_hash,
    )

    # Call model
    response = await model.complete(
        messages=[{"role": "user", "content": formatted_prompt}],
        temperature=0.0,
        max_tokens=8192,
    )

    # Parse response - expect JSON with blocks
    try:
        content = response.content
        parsed = json.loads(content)

        blocks = []
        unmet_deliverables = []

        for block_data in parsed.get("blocks", []):
            block_id = block_data.get("block_id", f"b{len(blocks)+1}")
            kind = block_data.get("kind", "general_explanation")
            spans = []

            for span_data in block_data.get("spans", []):
                if isinstance(span_data, str):
                    spans.append(span_data)
                elif isinstance(span_data, dict):
                    span_type = span_data.get("type")
                    if span_type == "value":
                        spans.append(create_value_span(
                            evidence_id=CanonicalUUID(span_data["evidence_id"]),
                            row_locator=span_data.get("row_locator", 0),
                            column_ordinal=span_data.get("column_ordinal", 0),
                            value=span_data["value"],
                            format=span_data.get("format", "exact"),
                            unit=span_data.get("unit"),
                        ))
                    elif span_type == "chart":
                        spans.append(create_chart_span(
                            chart_artifact_id=CanonicalUUID(span_data["chart_artifact_id"]),
                            caption=span_data.get("caption", ""),
                        ))
                    else:
                        spans.append(str(span_data))
                else:
                    spans.append(str(span_data))

            supports = block_data.get("supports", [])
            block = create_block(
                block_id=block_id,
                kind=kind,
                spans=spans,
                supports=supports,
            )
            blocks.append(block)

        for ud in parsed.get("unmet_deliverables", []):
            unmet_deliverables.append(
                TypedDraft.UnmetDeliverable(
                    description=ud.get("description", ""),
                    reason=ud.get("reason", ""),
                    required_evidence=ud.get("required_evidence"),
                )
            )

        typed_draft = TypedDraft(
            draft_id=CanonicalUUID(str(UUID(int=0))),  # Will be overwritten by caller
            blocks=blocks,
            unmet_deliverables=unmet_deliverables,
        )

        # Validate draft
        engine = DraftingEngine()
        # In real implementation, fetch evidence from ledger
        evidence = {}
        validation_errors = engine.validate_draft(typed_draft, evidence)

        if validation_errors:
            return Blocked(
                explanation="Draft validation failed",
                requirements=[{"kind": "validation", "description": e} for e in validation_errors],
            )

        completeness = "complete" if not unmet_deliverables else "partial"
        return DraftReady(draft=typed_draft, completeness=completeness)

    except json.JSONDecodeError:
        return Failed(error_ref="parse_error", stage="drafting")
    except Exception as e:
        return Failed(error_ref=f"drafting_error: {type(e).__name__}", stage="drafting")


class AnswerSpecialist:
    """Answer specialist for evidence-grounded drafting."""

    def __init__(self, context: WrapperContext) -> None:
        self._context = context
        self._engine = DraftingEngine()

    async def draft(self, request: AnswerInput, model: ModelGateway) -> AnswerOutcome:
        """Execute the drafting workflow."""
        return await draft(request, model=model)