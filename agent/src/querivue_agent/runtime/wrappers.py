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
from querivue_agent.runtime.graph_state import (
    RunState, SpecialistInput, SpecialistOutput, EvidenceRegistryEntry, ActionOutcome,
)


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
    # This would call the actual SQL specialist subgraph
    # For now, return a placeholder
    return SpecialistOutput(
        role="sql_specialist",
        invocation_id=input_.invocation_id,
        attempt=input_.attempt,
        status="succeeded",
        result={"type": "tabular_evidence", "rows": 0, "columns": []},
    )


async def python_specialist_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Python specialist."""
    return SpecialistOutput(
        role="python_specialist",
        invocation_id=input_.invocation_id,
        attempt=input_.attempt,
        status="succeeded",
        result={"type": "python_output", "artifacts": []},
    )


async def answer_specialist_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Answer specialist."""
    return SpecialistOutput(
        role="answer_specialist",
        invocation_id=input_.invocation_id,
        attempt=input_.attempt,
        status="succeeded",
        result={"type": "draft_ready", "draft": {}},
        requires_review=True,
    )


async def reviewer_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Reviewer."""
    return SpecialistOutput(
        role="reviewer",
        invocation_id=input_.invocation_id,
        attempt=input_.attempt,
        status="succeeded",
        result={"type": "assessment", "approved": True, "findings": []},
    )


async def clarification_agent_wrapper(
    input_: SpecialistInput,
    context: WrapperContext,
) -> SpecialistOutput:
    """Wrapper for Clarification Agent."""
    return SpecialistOutput(
        role="clarification_agent",
        invocation_id=input_.invocation_id,
        attempt=input_.attempt,
        status="succeeded",
        result={"type": "question_ready", "question": "Clarification needed?", "suggestions": []},
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