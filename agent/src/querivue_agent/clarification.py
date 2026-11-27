"""Clarification agent logic."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from querivue_agent.contracts.entry import EntryAccept, EntryReject, EntryClarify, EntryAssessment
from querivue_agent.contracts.inputs import ClarificationInput
from querivue_agent.contracts.actions import ClarificationAction
from querivue_agent.contracts.responses import ClarificationQuestionReady, ClarificationOutcome
from querivue_agent.contracts.content import BlockID, ClarificationTarget


async def ask_clarification(request: ClarificationInput, *, model) -> ClarificationOutcome:
    """Generate a clarification question."""
    # For T13, implement a basic clarification that asks for disambiguation
    # In reality, this would call the model gateway

    issue = request.request.issue
    candidate_interpretations = request.request.candidate_interpretations

    # Build clarification question
    question = ClarificationQuestionReady(
        question_id=uuid4(),
        issue=issue,
        candidate_interpretations=[
            {
                "candidate_id": ci.candidate_id,
                "interpretation": ci.interpretation,
                "basis_refs": [{"kind": "support", "target_id": str(ref)} for ref in ci.basis_refs],
            }
            for ci in candidate_interpretations
        ],
        options=[],
        content_hash="",  # Would be computed
        constraints=request.request.constraints.model_dump() if hasattr(request.request.constraints, 'model_dump') else {},
    )

    return ClarificationOutcome(
        type="clarification_outcome",
        question=question,
        evidence_ids=[],
        chart_artifact_ids=[],
    )


async def assess_entry(request, *, model) -> EntryAssessment:
    """Assess entry input for intake."""
    # For T13, implement basic entry assessment
    # In reality, this would call the model gateway

    # Simple heuristic: accept analytical questions, reject non-analytical
    question = getattr(request, 'question', '')
    keywords = ['what', 'how', 'why', 'when', 'where', 'which', 'total', 'sum', 'average', 'count', 'filter', 'show', 'get', 'list', 'select']
    if any(keyword in question.lower() for keyword in keywords):
        return EntryAccept(
            disposition="accept",
            policy_reason="analytical_question",
            explanation="Question accepted for analysis",
        )
    elif "?" in question:
        return EntryClarify(
            disposition="clarify",
            policy_reason="ambiguous_question",
            explanation="Question needs clarification",
            question="Please clarify what you'd like to analyze",
        )
    else:
        return EntryReject(
            disposition="reject",
            policy_reason="non_analytical",
            explanation="Input is not an analytical question",
        )