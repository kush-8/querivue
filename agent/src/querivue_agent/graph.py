"""Outer graph compilation and run orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from querivue_agent.runtime.authority import Authority
from querivue_agent.runtime.budgets import BudgetSnapshot
from querivue_agent.runtime.graph_state import (
    RunState,
    create_initial_run_state,
    SpecialistInput,
    SpecialistOutput,
)
from querivue_agent.runtime.wrappers import (
    WrapperContext,
    run_specialist,
    get_specialist_wrapper,
    get_input_builder,
    validate_specialist_output,
)
from querivue_agent.runtime.models import ModelGateway
from querivue_agent.runtime.trace import TraceRecorder
from querivue_agent.storage.artifacts import ArtifactStore
from querivue_agent.context import build_supervisor_input
from querivue_agent.supervisor import run_supervisor_step
from querivue_agent.dispatch import dispatch_queue, execute_current_task, run_review, run_answer
from querivue_agent.contracts.records import AdmissionReceipt, OwnerFence, Task
from querivue_agent.contracts.control import SupervisorDecision
from querivue_agent.contracts.common import Scope


@dataclass(frozen=True)
class RunConfig:
    """Configuration for a graph run."""
    max_iterations: int = 50
    max_sql_actions: int = 8
    max_python_actions: int = 8
    max_review_passes: int = 2
    checkpoint_interval: int = 1  # checkpoint every N steps


@dataclass(frozen=True)
class GraphProjection:
    """Projection of a restored run from checkpoints."""
    run_state: RunState
    checkpoint_id: str
    is_fresh: bool


async def _admission_node(state: RunState, context: WrapperContext) -> RunState:
    """Entry node - run is already admitted, just initialize."""
    state.phase = "planning"
    state.execution_status["phase"] = "planning"
    state.execution_status["queue_revision"] = 0
    state.execution_status["analysis_started"] = False
    return state


async def _supervisor_node(state: RunState, context: WrapperContext) -> RunState:
    """Supervisor decision node."""
    return await run_supervisor_step(state, context)


async def _dispatch_node(state: RunState, context: WrapperContext) -> RunState:
    """Dispatch queue node - convert supervisor decisions to committed tasks."""
    # Build supervisor input to get the latest decision
    from querivue_agent.context import build_supervisor_input

    supervisor_input = build_supervisor_input(
        run_state=state,
        pending_tasks=state.pending_tasks,
        current_task=state.current_task,
        environment_manifest_id=UUID("00000000-0000-0000-0000-000000000000"),
        policy_version="1.0",
        configuration_hash="config-v1",
        queue_revision=state.execution_status.get("queue_revision", 0),
        analysis_started=state.execution_status.get("analysis_started", False),
    )

    # Get decision from model gateway
    from querivue_agent.supervisor import decide
    decision = await decide(supervisor_input, model=context.model_gateway)

    # Apply decision via authority
    if decision.type == "propose_queue":
        state.pending_tasks = decision.pending_tasks
        state.execution_status["queue_revision"] = state.execution_status.get("queue_revision", 0) + 1
        state.execution_status["analysis_started"] = True
        state.phase = "analysis"

    return state


async def _execute_node(state: RunState, context: WrapperContext) -> RunState:
    """Execute current task's actions."""
    return await execute_current_task(state, context)


async def _answer_node(state: RunState, context: WrapperContext) -> RunState:
    """Answer specialist node."""
    return await run_answer(state, context)


async def _review_node(state: RunState, context: WrapperContext) -> RunState:
    """Review node."""
    if state.active_review_id and state.active_draft_id:
        return await run_review(state, state.active_draft_id, context)
    state.phase = "finalization"
    return state


async def _finalize_node(state: RunState, context: WrapperContext) -> RunState:
    """Finalize run."""
    state.phase = "terminal"
    return state


def _should_continue_execution(state: RunState) -> Literal["supervisor", "execute", "answer", "review", "finalize", "end"]:
    """Determine next node based on phase."""
    phase = state.phase
    if phase == "planning":
        return "supervisor"
    elif phase == "analysis":
        if state.current_task and state.pending_tasks:
            return "execute"
        else:
            return "answer"
    elif phase == "answer":
        if state.active_draft_id:
            return "review"
        return "finalize"
    elif phase == "review":
        return "review"
    elif phase == "finalization":
        return "finalize"
    elif phase == "terminal":
        return "end"
    return "end"


def build_graph(
    *,
    authority: Authority,
    model_gateway: ModelGateway,
    trace_recorder: TraceRecorder,
    artifact_store: ArtifactStore,
    checkpointer: BaseCheckpointSaver,
    config: RunConfig,
) -> CompiledStateGraph:
    """Compile the outer graph with private specialist subgraphs."""

    # Build wrapper context
    context = WrapperContext(
        run_state=None,  # Will be set per-invocation
        model_gateway=model_gateway,
        trace_recorder=trace_recorder,
        authority=authority,
        artifact_store=artifact_store,
    )

    # Create state graph
    graph = StateGraph(RunState)

    # Add nodes
    graph.add_node("admission", lambda s: _admission_node(s, context))
    graph.add_node("supervisor", lambda s: _supervisor_node(s, context))
    graph.add_node("dispatch", lambda s: _dispatch_node(s, context))
    graph.add_node("execute", lambda s: _execute_node(s, context))
    graph.add_node("answer", lambda s: _answer_node(s, context))
    graph.add_node("review", lambda s: _review_node(s, context))
    graph.add_node("finalize", lambda s: _finalize_node(s, context))

    # Add edges
    graph.add_edge(START, "admission")
    graph.add_edge("admission", "supervisor")

    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor",
        _should_continue_execution,
        {
            "supervisor": "supervisor",
            "execute": "execute",
            "answer": "answer",
            "review": "review",
            "finalize": "finalize",
            "end": END,
        }
    )

    # After dispatch, go to execute or answer
    graph.add_conditional_edges(
        "dispatch",
        _should_continue_execution,
        {
            "execute": "execute",
            "answer": "answer",
            "review": "review",
            "finalize": "finalize",
            "end": END,
        }
    )

    # After execute, go back to supervisor
    graph.add_conditional_edges(
        "execute",
        _should_continue_execution,
        {
            "supervisor": "supervisor",
            "execute": "execute",
            "answer": "answer",
            "review": "review",
            "finalize": "finalize",
            "end": END,
        }
    )

    # After answer, go to review or finalize
    graph.add_conditional_edges(
        "answer",
        _should_continue_execution,
        {
            "review": "review",
            "finalize": "finalize",
            "end": END,
        }
    )

    # After review, go back to supervisor or finalize
    graph.add_conditional_edges(
        "review",
        _should_continue_execution,
        {
            "supervisor": "supervisor",
            "finalize": "finalize",
            "end": END,
        }
    )

    # Finalize goes to end
    graph.add_edge("finalize", END)

    # Compile with checkpointer
    compiled = graph.compile(checkpointer=checkpointer)

    return compiled


async def submit(
    request: dict,
    *,
    scope: Scope,
    config: RunConfig,
    authority: Authority,
    model_gateway: ModelGateway,
    trace_recorder: TraceRecorder,
    artifact_store: ArtifactStore,
    checkpointer: BaseCheckpointSaver,
) -> RunState:
    """Submit a new run and return initial state."""
    # This would be the entry point for CLI
    # For now, return a placeholder
    run_id = uuid4()
    project_id = scope.project_id
    chat_id = scope.chat_id
    question = request.get("question", "")
    eligible_dataset_ids = scope.eligible_dataset_ids

    # Create admission receipt (placeholder)
    admission_receipt = AdmissionReceipt(
        run_id=run_id,
        project_id=project_id,
        chat_id=chat_id,
        scope=scope,
        admitted=True,
        reason="automatic",
    )

    fence = OwnerFence(
        owner_id=chat_id,
        generation=1,
        scope=scope,
    )

    budget = BudgetSnapshot(
        run_id=run_id,
        project_id=project_id,
        counters={},
        revision=0,
    )

    deadline = "2099-12-31T23:59:59Z"

    return create_initial_run_state(
        run_id=run_id,
        project_id=project_id,
        chat_id=chat_id,
        question=question,
        eligible_dataset_ids=eligible_dataset_ids,
        admission_receipt=admission_receipt,
        fence=fence,
        budget=budget,
        deadline=deadline,
    )


async def build_packet(
    role: str,
    run_id: UUID,
    scope: Scope,
    fence: OwnerFence,
) -> Any:
    """Build a specialist input packet from run state."""
    # This would load run state and build the appropriate packet
    # Placeholder for T13
    pass


async def restore_run(
    run_id: UUID,
    *,
    authority: Authority,
    checkpointer: BaseCheckpointSaver,
    config: RunConfig,
) -> GraphProjection:
    """Restore a run from checkpoints."""
    # Get latest checkpoint
    # This would use the checkpointer to restore state
    # Placeholder for T16
    pass


def create_graph_projection(
    run_state: RunState,
    checkpoint_id: str,
    is_fresh: bool = False,
) -> GraphProjection:
    """Create a graph projection from run state."""
    return GraphProjection(
        run_state=run_state,
        checkpoint_id=checkpoint_id,
        is_fresh=is_fresh,
    )