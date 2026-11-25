"""Entry assessment logic."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from querivue_agent.contracts.entry import EntryInput, EntryAccept, EntryReject, EntryClarify, EntryAssessment
from querivue_agent.contracts.inputs import EntryInput as RoleEntryInput
from querivue_agent.context import build_entry_input


async def assess_entry(request: EntryInput, *, model) -> EntryAssessment:
    """Assess an entry input for admission."""
    # For T13, implement basic entry assessment
    # In reality, this would call the model gateway

    question = request.question

    # Simple heuristic: accept analytical questions
    analytical_keywords = ['what', 'how', 'why', 'when', 'where', 'which', 'total', 'sum', 'average', 'count', 'compare', 'analyze', 'breakdown']
    if any(keyword in question.lower() for keyword in analytical_keywords):
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


async def run_entry_assessment(
    request: EntryInput,
    scope: Scope,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    model,
) -> EntryAssessment:
    """Run entry assessment and return outcome."""
    # Build entry input packet for model
    # For T13, we use a simplified approach
    return await assess_entry(request, model=model)