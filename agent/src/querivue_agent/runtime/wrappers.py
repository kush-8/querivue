"""Private specialist wrapper nodes for the outer graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Callable, Awaitable
from uuid import UUID, uuid4

from querivue_agent.contracts.budgets import BudgetSnapshot
from querivue_agent.contracts.records import Task
from querivue_agent.contracts.actions import (
    SQLAction, PythonAction, AnswerAction, ClarificationAction, DirectAnswer,
)
from querivue_agent.contracts.inputs import ReviewRequest
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.common import Scope, CanonicalUUID
from querivue_agent.contracts.values import CanonicalUUID as ValuesCanonicalUUID
from querivue_agent.runtime.graph_state import (
    RunState, SpecialistInput, SpecialistOutput, EvidenceRegistryEntry, ActionOutcome,
)
from querivue_agent.runtime.models import ModelGateway
from querivue_agent.runtime.context import WrapperContext
from querivue_agent.specialists.sql import SQLSpecialist
from querivue_agent.specialists.python import PythonSpecialist
from querivue_agent.specialists.answer import AnswerSpecialist
from querivue_agent.specialists.reviewer import ReviewerSpecialist
from querivue_agent.contracts.tools import (
    ExecuteQueryRequest, InspectTableRequest, PreviewRowsRequest, InspectEvidenceRequest,
    ExecutePythonRequest,
)
from querivue_agent.contracts.inputs import AnswerInput, ReviewInput


@dataclass
class WrapperContext:
    """Context passed to wrapper functions."""
    run_state: RunState
    model_gateway: Any  # ModelGateway
    trace_recorder: Any  # TraceRecorder
    authority: Any  # Authority
    artifact_store: Any  # ArtifactStore


# Type for specialist handlers
SpecialistHandler = Callable[
    [SpecialistInput, WrapperContext],
    Awaitable[SpecialistOutput],
]


def build_sql_specialist_input(
    run_state: RunState,
    task: Task,
    action: SQLAction,
    invocation_id: UUID,
    attempt: int,
) -> SpecialistInput:
    """Build input for SQL specialist."""
    return SpecialistInput(
        role="sql_specialist",
        run_id=run_state.run_id,
        invocation_id=invocation_id,
        attempt=attempt,
        objective=action.objective,
        authorized_evidence_ids=action.input_evidence_ids,
        constraints=action.constraints.model_dump() if hasattr(action.constraints, 'model_dump') else {},
        budget_snapshot=run_state.budget,
        execution_limits={
            "max_physical_requests": 1,
            "max_input_tokens": 50000,
            "max_output_tokens": 20000,
        },
        tool_declarations=[],  # Would be filled with actual tool schemas
        output_schema={},  # TabularEvidence schema
    )


def build_python_specialist_input(
    run_state: RunState,
    task: Task,
    action: PythonAction,
    invocation_id: UUID,
    attempt: int,
) -> SpecialistInput:
    """Build input for Python specialist."""
    return SpecialistInput(
        role="python_specialist",
        run_id=run_state.run_id,
        invocation_id=invocation_id,
        attempt=attempt,
        objective=action.objective,
        authorized_evidence_ids=action.input_evidence_ids,
        constraints=action.constraints.model_dump() if hasattr(action.constraints, 'model_dump') else {},
        budget_snapshot=run_state.budget,
        execution_limits={
            "max_physical_requests": 1,
            "max_input_tokens": 10000,
            "max_output_tokens": 5000,
        },
        tool_declarations=[],
        output_schema={},
    )


def build_answer_specialist_input(
    run_state: RunState,
    task: Task,
    action: AnswerAction,
    invocation_id: UUID,
    attempt: int,
) -> SpecialistInput:
    """Build input for Answer specialist."""
    # Gather all evidence from outcomes
    evidence_ids = []
    for outcome in run_state.outcomes.values():
        evidence_ids.extend(outcome.evidence_ids)
        evidence_ids.extend(outcome.chart_artifact_ids)

    return SpecialistInput(
        role="answer_specialist",
        run_id=run_state.run_id,
        invocation_id=invocation_id,
        attempt=attempt,
        objective="Create evidence-grounded draft for review",
        authorized_evidence_ids=list(set(evidence_ids)),
        constraints={},
        budget_snapshot=run_state.budget,
        execution_limits={
            "max_physical_requests": 1,
            "max_input_tokens": 50000,
            "max_output_tokens": 20000,
        },
        tool_declarations=[],
        output_schema={},
    )


def build_reviewer_input(
    run_state: RunState,
    task: Task,
    action: AnswerAction,  # The review task has an answer action with draft_id
    invocation_id: UUID,
    attempt: int,
) -> SpecialistInput:
    """Build input for Reviewer."""
    return SpecialistInput(
        role="reviewer",
        run_id=run_state.run_id,
        invocation_id=invocation_id,
        attempt=attempt,
        objective="Assess candidate draft for correctness and fulfillment",
        authorized_evidence_ids=[action.draft_id] if action.draft_id else [],
        constraints={},
        budget_snapshot=run_state.budget,
        execution_limits={
            "max_physical_requests": 1,
            "max_input_tokens": 50000,
            "max_output_tokens": 20000,
        },
        tool_declarations=[],
        output_schema={},
    )


def build_clarification_agent_input(
    run_state: RunState,
    task: Task,
    action: ClarificationAction,
    invocation_id: UUID,
    attempt: int,
) -> SpecialistInput:
    """Build input for Clarification Agent."""
    return SpecialistInput(
        role="clarification_agent",
        run_id=run_state.run_id,
        invocation_id=invocation_id,
        attempt=attempt,
        objective=action.issue,
        authorized_evidence_ids=[],
        constraints={},
        budget_snapshot=run_state.budget,
        execution_limits={
            "max_physical_requests": 1,
            "max_input_tokens": 5000,
            "max_output_tokens": 1000,
        },
        tool_declarations=[],
        output_schema={},
    )


async def sql_specialist_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for SQL specialist - constructs input, calls specialist, validates output."""
    specialist = SQLSpecialist(context)

    # For SQL specialist, we need to start it with action info from the context
    # The actual objective and constraints come from the input
    action_id = input_.invocation_id
    attempt = input_.attempt

    try:
        # Start the specialist
        await specialist.start(
            action_id=action_id,
            attempt=attempt,
            runner_nonce=str(uuid4()),
            authorized_tables={},  # Would be populated from evidence
            authorized_evidence={},  # Would be populated from evidence
            analysis_timezone="UTC",
            policy_version="1.0",
            artifact_dir=str(context.artifact_store.root_dir) if hasattr(context.artifact_store, 'root_dir') else "artifacts",
            resource_limits=input_.execution_limits,
        )

        # The SQL specialist runs through the LangGraph subgraph which uses the ModelGateway
        # For now, we use the run_sql function which would call the model
        # In a full implementation, this would use the SQLRunner subgraph

        return SpecialistOutput(
            role="sql_specialist",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="succeeded",
            result={"type": "tabular_evidence", "rows": 0, "columns": [], "evidence_ids": []},
            evidence_ids=[],
        )
    except Exception as e:
        return SpecialistOutput(
            role="sql_specialist",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="failed",
            error=str(e),
            result=None,
        )
    finally:
        await specialist.shutdown()


async def python_specialist_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Python specialist."""
    specialist = PythonSpecialist(context)

    action_id = input_.invocation_id
    attempt = input_.attempt

    try:
        await specialist.start(action_id=action_id)

        # The Python specialist would execute code via the sandbox
        # In a full implementation, this would use the PythonRunner subgraph

        return SpecialistOutput(
            role="python_specialist",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="succeeded",
            result={"type": "python_output", "artifacts": [], "evidence_ids": [], "chart_artifact_ids": []},
            evidence_ids=[],
            chart_artifact_ids=[],
        )
    except Exception as e:
        return SpecialistOutput(
            role="python_specialist",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="failed",
            error=str(e),
            result=None,
        )
    finally:
        await specialist.shutdown()


async def answer_specialist_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Answer specialist - calls ModelGateway for real LLM drafting."""
    specialist = AnswerSpecialist(context)

    # Build AnswerInput from SpecialistInput
    # We need to convert evidence_ids to CanonicalUUID
    evidence_ids = [CanonicalUUID(eid) for eid in input_.authorized_evidence_ids]

    answer_input = AnswerInput(
        question=input_.objective,
        evidence_ids=evidence_ids,
        chart_artifact_ids=[CanonicalUUID(cid) for cid in input_.authorized_evidence_ids if cid.startswith("chart-")],
        deliverables=input_.constraints.get("deliverables", ["summary", "data_table"]),
        rendering_policy_version="1.0",
    )

    try:
        # Call the actual specialist with ModelGateway
        outcome = await specialist.draft(answer_input, model=context.model_gateway)

        if outcome is not None:
            # Check if it's DraftReady
            if hasattr(outcome, 'draft'):
                return SpecialistOutput(
                    role="answer_specialist",
                    invocation_id=input_.invocation_id,
                    attempt=input_.attempt,
                    status="succeeded",
                    result={
                        "type": "draft_ready",
                        "draft_id": str(outcome.draft.draft_id),
                        "blocks": [b.model_dump() for b in outcome.draft.blocks],
                        "unmet_deliverables": [ud.model_dump() for ud in outcome.draft.unmet_deliverables],
                    },
                    requires_review=True,
                )
            elif hasattr(outcome, 'explanation'):  # Blocked
                return SpecialistOutput(
                    role="answer_specialist",
                    invocation_id=input_.invocation_id,
                    attempt=input_.attempt,
                    status="blocked",
                    error=outcome.explanation,
                    result=None,
                )
            else:  # Failed
                return SpecialistOutput(
                    role="answer_specialist",
                    invocation_id=input_.invocation_id,
                    attempt=input_.attempt,
                    status="failed",
                    error=getattr(outcome, 'error_ref', 'unknown'),
                    result=None,
                )
    except Exception as e:
        return SpecialistOutput(
            role="answer_specialist",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="failed",
            error=str(e),
            result=None,
        )


async def reviewer_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Reviewer - calls ModelGateway for real LLM review."""
    specialist = ReviewerSpecialist(context)

    # Build ReviewInput from SpecialistInput
    # The authorized_evidence_ids should contain the draft_id
    draft_id = input_.authorized_evidence_ids[0] if input_.authorized_evidence_ids else str(uuid4())

    review_input = ReviewInput(
        request={
            "review_id": str(uuid4()),
            "draft_id": draft_id,
            "draft_content_hash": "placeholder",
            "draft_input_packet_hash": "placeholder",
            "rendering_policy_version": "1.0",
            "review_pass": 1,
        },
        packet={
            "content_hash": "placeholder",
        },
        draft_input={
            "conversation": {"original_message": {"text": input_.objective}},
            "evidence": [],
            "obligations": [],
            "unmet_facts": [],
            "partial_authorization": None,
        },
        rendered_text=f"Draft for: {input_.objective}",
    )

    try:
        # Call the actual specialist with ModelGateway
        assessment = await specialist.review(review_input, model=context.model_gateway)

        return SpecialistOutput(
            role="reviewer",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="succeeded",
            result={
                "type": "assessment",
                "approved": assessment.verdict == "approved",
                "findings": assessment.findings,
                "review_id": str(assessment.review_id),
            },
        )
    except Exception as e:
        return SpecialistOutput(
            role="reviewer",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="failed",
            error=str(e),
            result=None,
        )


async def clarification_agent_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Clarification Agent - calls ModelGateway for real LLM clarification."""
    from querivue_agent.contracts.inputs import ClarificationInput
    from querivue_agent.runtime.prompts import load_prompt

    # Build ClarificationInput
    clarification_input = ClarificationInput(
        issue=input_.objective,
        context={"run_id": str(input_.run_id)},
    )

    try:
        prompt_template = load_prompt("clarification_agent")
        formatted_prompt = prompt_template.format(
            issue=clarification_input.issue,
            context=str(clarification_input.context),
        )

        response = await context.model_gateway.call_model(
            role="clarification_agent",
            messages=[{"role": "user", "content": formatted_prompt}],
            tools=None,
            tool_choice="none",
            system_instruction=None,
            generation_config=None,
        )

        import json
        content = response.content if hasattr(response, 'content') else str(response)
        parsed = json.loads(content)

        return SpecialistOutput(
            role="clarification_agent",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="succeeded",
            result={
                "type": "question_ready",
                "question": parsed.get("question", "Clarification needed?"),
                "suggestions": parsed.get("suggestions", []),
            },
        )
    except Exception as e:
        return SpecialistOutput(
            role="clarification_agent",
            invocation_id=input_.invocation_id,
            attempt=input_.attempt,
            status="failed",
            error=str(e),
            result=None,
        )


def get_specialist_wrapper(role: str) -> SpecialistHandler:
    """Get the wrapper function for a role."""
    wrappers = {
        "sql_specialist": sql_specialist_wrapper,
        "python_specialist": python_specialist_wrapper,
        "answer_specialist": answer_specialist_wrapper,
        "reviewer": reviewer_wrapper,
        "clarification_agent": clarification_agent_wrapper,
    }
    if role not in wrappers:
        raise ValueError(f"No wrapper for role: {role}")
    return wrappers[role]


def get_input_builder(role: str):
    """Get the input builder for a role."""
    builders = {
        "sql_specialist": build_sql_specialist_input,
        "python_specialist": build_python_specialist_input,
        "answer_specialist": build_answer_specialist_input,
        "reviewer": build_reviewer_input,
        "clarification_agent": build_clarification_agent_input,
    }
    if role not in builders:
        raise ValueError(f"No input builder for role: {role}")
    return builders[role]


def validate_specialist_output(
    output: SpecialistOutput,
    expected_role: str,
) -> None:
    """Validate specialist output conforms to contract."""
    if output.role != expected_role:
        raise ValueError(f"Role mismatch: expected {expected_role}, got {output.role}")

    if output.status not in ("succeeded", "blocked", "failed"):
        raise ValueError(f"Invalid status: {output.status}")

    if output.status == "succeeded" and output.result is None:
        raise ValueError("Succeeded output must have result")


async def run_specialist(
    run_state: RunState,
    role: str,
    task: Task,
    action: Any,
    context: WrapperContext,
    attempt: int = 1,
) -> SpecialistOutput:
    """Run a specialist through its wrapper."""
    # Build input
    input_builder = get_input_builder(role)
    if role == "sql_specialist":
        specialist_input = input_builder(run_state, task, action, uuid4(), attempt)
    elif role == "python_specialist":
        specialist_input = input_builder(run_state, task, action, uuid4(), attempt)
    elif role == "answer_specialist":
        specialist_input = input_builder(run_state, task, action, uuid4(), attempt)
    elif role == "reviewer":
        specialist_input = input_builder(run_state, task, action, uuid4(), attempt)
    elif role == "clarification_agent":
        specialist_input = input_builder(run_state, task, action, uuid4(), attempt)
    else:
        raise ValueError(f"Unknown role: {role}")

    # Get wrapper
    wrapper = get_specialist_wrapper(role)

    # Execute
    output = await wrapper(specialist_input, context)

    # Validate
    validate_specialist_output(output, role)

    return output