"""Graph state definitions for the agent outer graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.budgets import BudgetSnapshot
from querivue_agent.contracts.common import Scope, OwnerFence
from querivue_agent.contracts.records import (
    AdmissionReceipt,
    QueueReceipt,
    Task,
    ReviewReservation,
)
from querivue_agent.contracts.control import SupervisorDecision
from querivue_agent.contracts.actions import (
    SQLAction,
    PythonAction,
    AnswerAction,
    ClarificationAction,
    DirectAnswer,
)
from querivue_agent.contracts.inputs import ReviewRequest
from querivue_agent.contracts.artifacts import ArtifactRef
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.entry import EntryAccept, EntryReject, EntryClarify


@dataclass(frozen=True)
class EvidenceRegistryEntry:
    """An entry in the run's evidence registry."""
    evidence_id: UUID
    evidence_type: Literal["tabular", "chart", "python_output"]
    producer: Literal["sql", "python"]
    method: str  # e.g., "execute_query", "python_artifact"
    schema: dict[str, Any]  # Column names and types
    row_count: int
    source_dependencies: list[UUID]  # Dataset/source IDs
    integrity_hash: str
    artifact_ref: str  # Reference to full artifact
    preview: dict[str, Any]  # Bounded preview with coverage/locators
    created_at: str
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))


@dataclass(frozen=True)
class ActionOutcome:
    """Terminal outcome of an action."""
    task_id: UUID
    action_id: UUID
    attempt: int
    result_ref: str  # Durable reference to the result
    result: dict[str, Any]  # The actual component result
    evidence_ids: list[UUID] = field(default_factory=list)
    chart_artifact_ids: list[UUID] = field(default_factory=list)
    status: Literal["succeeded", "blocked", "failed"] = "succeeded"
    error: dict[str, Any] | None = None


@dataclass
class RunState:
    """Parent state for the outer graph."""
    # Immutable input
    run_id: UUID
    project_id: UUID
    chat_id: UUID
    question: str
    eligible_dataset_ids: list[UUID]
    admission_receipt: AdmissionReceipt | None = None
    fence: OwnerFence | None = None

    # Runtime-built context packet for supervisor
    context: dict[str, Any] = field(default_factory=dict)

    # Evidence registry - single source of truth for evidence in this run
    evidence: dict[str, EvidenceRegistryEntry] = field(default_factory=dict)

    # Bounded supervisor-local messages
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Task queue management
    pending_tasks: list[Task] = field(default_factory=list)
    current_task: Task | None = None

    # Action outcomes keyed by action_id
    outcomes: dict[str, ActionOutcome] = field(default_factory=dict)

    # Runtime-owned execution status
    execution_status: dict[str, Any] = field(default_factory=dict)

    # Final output (null until finalized)
    output: dict[str, Any] | None = None

    # Budget tracking
    budget: BudgetSnapshot | None = None

    # Deadline tracking
    deadline: str | None = None

    # Current phase
    phase: Literal[
        "admitted", "planning", "analysis", "answer", "review",
        "clarification", "waiting", "finalization", "terminal"
    ] = "admitted"

    # Active review/clarification records
    active_review_id: UUID | None = None
    active_review_pass: int = 0
    active_clarification_id: UUID | None = None

    # Draft tracking
    active_draft_id: UUID | None = None
    active_draft_predecessor: UUID | None = None

    def get_evidence_by_id(self, evidence_id: UUID) -> EvidenceRegistryEntry | None:
        """Get evidence entry by ID."""
        return self.evidence.get(str(evidence_id))

    def get_outcome_by_action(self, action_id: UUID) -> ActionOutcome | None:
        """Get outcome for an action."""
        return self.outcomes.get(str(action_id))

    def register_evidence(self, entry: EvidenceRegistryEntry) -> None:
        """Register evidence in the registry (idempotent)."""
        key = str(entry.evidence_id)
        if key in self.evidence:
            existing = self.evidence[key]
            if existing.integrity_hash != entry.integrity_hash:
                raise ValueError(f"Evidence integrity mismatch for {key}")
        else:
            self.evidence[key] = entry

    def commit_outcome(self, outcome: ActionOutcome) -> None:
        """Commit an action outcome."""
        key = str(outcome.action_id)
        if key in self.outcomes:
            existing = self.outcomes[key]
            if existing.attempt != outcome.attempt:
                raise ValueError(f"Attempt mismatch for {key}")
            # Same attempt - idempotent
            if existing.result_ref != outcome.result_ref:
                raise ValueError(f"Result ref mismatch for {key}")
        else:
            self.outcomes[key] = outcome


@dataclass(frozen=True)
class SpecialistInput:
    """Input contract for specialist wrappers."""
    role: Literal["sql_specialist", "python_specialist", "answer_specialist", "reviewer", "clarification_agent"]
    run_id: UUID
    invocation_id: UUID
    attempt: int
    objective: str
    authorized_evidence_ids: list[UUID]
    constraints: dict[str, Any]
    budget_snapshot: BudgetSnapshot
    execution_limits: dict[str, Any]
    tool_declarations: list[dict[str, Any]]
    output_schema: dict[str, Any]


@dataclass(frozen=True)
class SpecialistOutput:
    """Output contract for specialist wrappers."""
    role: Literal["sql_specialist", "python_specialist", "answer_specialist", "reviewer", "clarification_agent"]
    invocation_id: UUID
    attempt: int
    status: Literal["succeeded", "blocked", "failed"]
    result: dict[str, Any] | None
    evidence_ids: list[UUID] = field(default_factory=list)
    chart_artifact_ids: list[UUID] = field(default_factory=list)
    error: dict[str, Any] | None = None
    requires_review: bool = False


def create_initial_run_state(
    run_id: UUID,
    project_id: UUID,
    chat_id: UUID,
    question: str,
    eligible_dataset_ids: list[UUID],
    admission_receipt: AdmissionReceipt,
    fence: OwnerFence,
    budget: BudgetSnapshot,
    deadline: str,
) -> RunState:
    """Create initial run state from admission."""
    return RunState(
        run_id=run_id,
        project_id=project_id,
        chat_id=chat_id,
        question=question,
        eligible_dataset_ids=eligible_dataset_ids,
        admission_receipt=admission_receipt,
        fence=fence,
        budget=budget,
        deadline=deadline,
        execution_status={
            "phase": "planning",
            "owner_generation": fence.generation,
            "expected_attempt": 1,
            "review_passes_used": 0,
            "review_passes_remaining": 2,
            "active_draft_id": None,
            "active_review_id": None,
        },
    )