"""Guarded authority transitions for domain state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from querivue_agent.contracts.budgets import (
    BudgetSnapshot,
    ReservationRequest,
    CounterAmounts,
    ProtectedReserve,
)
from querivue_agent.contracts.budgets import ClockReading
from querivue_agent.contracts.common import OwnerFence, Scope
from querivue_agent.contracts.entry import EntryInput as IntakeEntryInput
from querivue_agent.contracts.inputs import ReviewInput
from querivue_agent.contracts.records import (
    AdmissionReceipt,
    AdmissionTarget,
    DeletionReceipt,
    FinalCandidate,
    FinalResult,
    IntakeAdmission,
    IntakeReceipt,
    LinkedReply,
    ModelCompletion,
    ModelReservation,
    ModelRequest,
    OperationRequest,
    QueueReceipt,
    ResumeReceipt,
    ReviewReservation,
)
from querivue_agent.runtime.budgets import check_reservation, create_initial_budget
from querivue_agent.storage.ledger import Ledger, LedgerOps


class Authority:
    """Single authority for all domain transitions - no raw Ledger SQL from gateway/controller."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger
        self._ops = LedgerOps(ledger)

    # --- Scope/Intake/Control entry points ---

    def initialize_scope(self, state_root: Path) -> Scope:
        """Initialize a new scope at state root."""
        project_id = str(uuid4())
        self._ops.create_project(project_id)
        return Scope(
            project_id=project_id,
            chat_id=None,
            run_id=None,
            eligible_dataset_ids=[],
        )

    def record_intake(self, request: IntakeEntryInput, scope: Scope) -> IntakeReceipt:
        """Record intake request and return receipt."""
        intake_id = str(uuid4())
        submission_key = f"intake-{intake_id}"
        original_hash = request.submission_hash
        fence_json = f'{{"subject_kind": "intake", "subject_id": "{intake_id}"}}'
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        expires_at = "2099-12-31T23:59:59.999999Z"

        self._ops.create_intake(
            intake_id=intake_id,
            submission_key=submission_key,
            project_id=scope.project_id,
            input_json=request.model_dump_json(),
            original_hash=original_hash,
            fence_json=fence_json,
            expires_at=expires_at,
        )

        # Create IntakeReceipt with proper types
        intake_receipt = IntakeReceipt(
            intake_id=intake_id,
            submission_key=submission_key,
            input=request,
            original_hash=original_hash,
            fence=OwnerFence(
                scope=scope,
                subject_kind="intake",
                subject_id=intake_id,
                owner_id=str(uuid4()),
                generation=1,
                attempt=1,
                expected_revision=0,
                lease_expires_at=expires_at,
            ),
            entry_question_id=None,
            outcome=None,
            created_at=created_at,
            expires_at=expires_at,
            status="pending",
            invocation_ids=[],
            charge_ref=None,
        )
        return intake_receipt

    def claim_run(self, run_id: UUID, owner_id: UUID) -> OwnerFence:
        """Claim run ownership."""
        lease_expires_at = "2099-12-31T23:59:59.999999Z"
        ok = self._ops.claim_run_ownership(str(run_id), str(owner_id), 2, lease_expires_at)
        if not ok:
            raise ValueError("failed to claim run ownership")

        # Get the run to find project_id and chat_id
        run = self._ops.get_run(str(run_id))
        project_id = run["project_id"] if run else ""
        chat_id = run["chat_id"] if run else None

        return OwnerFence(
            scope=Scope(project_id=project_id, chat_id=chat_id, run_id=run_id, eligible_dataset_ids=[]),
            subject_kind="run",
            subject_id=run_id,
            owner_id=str(owner_id),
            generation=2,
            attempt=1,
            expected_revision=0,
            lease_expires_at=lease_expires_at,
        )

    def renew_lease(self, fence: OwnerFence) -> OwnerFence:
        """Renew lease for run ownership."""
        lease_expires_at = "2099-12-31T23:59:59.999999Z"
        ok = self._ops.renew_lease(str(fence.subject_id), str(fence.owner_id), fence.generation, lease_expires_at)
        if not ok:
            raise ValueError("failed to renew lease")
        return OwnerFence(
            scope=fence.scope,
            subject_kind=fence.subject_kind,
            subject_id=fence.subject_id,
            owner_id=fence.owner_id,
            generation=fence.generation,
            attempt=fence.attempt,
            expected_revision=fence.expected_revision,
            lease_expires_at=lease_expires_at,
        )

    # --- Core authority transitions ---

    def admit(self, admission: IntakeAdmission) -> AdmissionReceipt:
        """Admit intake and create run."""
        run_id = str(uuid4())
        receipt_id = str(uuid4())
        admission_id = str(admission.admission_id)

        # Determine chat_id - use existing or create new for new questions
        chat_id = admission.scope.chat_id
        if chat_id is None:
            # For new questions without a chat, create a new chat
            chat_id = str(uuid4())
            self._ops.create_chat(chat_id, admission.scope.project_id)
        else:
            # Ensure chat exists (for existing chat_id)
            self._ops.create_chat(chat_id, admission.scope.project_id)

        # Create scope with run_id for the budget
        run_scope = Scope(
            project_id=admission.scope.project_id,
            chat_id=chat_id,
            run_id=run_id,
            eligible_dataset_ids=admission.scope.eligible_dataset_ids,
        )

        self._ops.create_intake_admission(
            admission_id=admission_id,
            intake_id=str(admission.intake_id),
            submission_hash=admission.submission_hash,
            scope_json=admission.scope.model_dump_json(),
            assessment_json=admission.assessment.model_dump_json(),
            context_hash=str(uuid4()),
            configuration_hash=admission.configuration_hash,
            policy_version=admission.policy_version,
            target_json=admission.target.model_dump_json(),
            fence_json=admission.fence.model_dump_json(),
        )

        initial_budget = create_initial_budget(run_scope)

        # Create the run first (needed for FK constraint)
        self._ops.create_run(
            run_id=run_id,
            project_id=admission.scope.project_id,
            chat_id=chat_id,
            question="",  # Would come from intake
            scope_hash=str(uuid4()),
            eligible_dataset_ids=admission.scope.eligible_dataset_ids,
            budget_json=initial_budget.model_dump_json(),
            configuration_hash=admission.configuration_hash,
            deadline=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        self._ops.create_admission_receipt(
            receipt_id=receipt_id,
            admission_id=admission_id,
            intake_id=str(admission.intake_id),
            run_id=run_id,
            scope_json=run_scope.model_dump_json(),
            cutoff_sequence=0,
            budget_json=initial_budget.model_dump_json(),
            configuration_hash=admission.configuration_hash,
        )

        return AdmissionReceipt(
            receipt_id=receipt_id,
            admission_id=admission_id,
            intake_id=admission.intake_id,
            run_id=run_id,
            scope=run_scope,
            cutoff_sequence=0,
            budget=initial_budget,
            configuration_hash=admission.configuration_hash,
            accepted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def commit_decision(
        self, run_id: UUID, proposal, fence: OwnerFence
    ) -> QueueReceipt:
        """Commit supervisor decision to queue."""
        # Validate the proposal - must be a valid SupervisorDecision
        # For now, we assume it's valid and just create the receipt
        receipt_id = str(uuid4())
        invocation_id = str(uuid4())  # Create a new invocation for this decision
        proposal_hash = hashlib.sha256(str(proposal).encode()).hexdigest()  # Valid SHA-256 hash

        # Create the invocation first for FK constraint
        self._ops.create_invocation(
            invocation_id=invocation_id,
            run_id=str(run_id),
            intake_id=None,
            role="supervisor",
            attempt=1,
            invocation_key="decision",
            packet_hash=proposal_hash,
            request_json='{}',
        )

        # Extract tasks from proposal for QueueReceipt and serialize
        tasks = getattr(proposal, 'tasks', [])
        tasks_json = [task.model_dump() for task in tasks]

        self._ops.record_queue_receipt(
            receipt_id=receipt_id,
            run_id=str(run_id),
            invocation_id=invocation_id,
            proposal_hash=proposal_hash,
            decision_type="propose_queue",
            previous_queue_revision=0,
            queue_revision=1,
            run_revision=1,
            task_mapping={},
            action_mapping={},
            tasks=tasks_json,
            withdrawn_task_ids=[],
        )
        return QueueReceipt(
            receipt_id=receipt_id,
            run_id=run_id,
            invocation_id=invocation_id,
            proposal_hash=proposal_hash,
            decision_type="propose_queue",
            previous_queue_revision=0,
            queue_revision=1,
            run_revision=1,
            task_mapping={},
            action_mapping={},
            tasks=tasks,
            withdrawn_task_ids=[],
        )

    def reserve_model(self, request: ModelRequest, fence: OwnerFence) -> ModelReservation:
        """Reserve model tokens and cost."""
        now = ClockReading(
            utc_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            monotonic_milliseconds=0,
            process_id=str(uuid4()),
            trusted=True,
        )

        # Get current budget from ledger
        run = self._ops.get_run(str(fence.scope.run_id))
        if run is None:
            raise ValueError("run not found")

        # For now, use initial budget - in reality would read from ledger
        current = create_initial_budget(fence.scope)

        # Convert ModelRequest to ReservationRequest
        reservation_request = ReservationRequest(
            request_id=request.request_id,
            scope=fence.scope,
            purpose="model",
            counters=CounterAmounts(
                physical_requests=1,
                logical_invocations=1,
                input_tokens=request.max_input_tokens,
                output_tokens=request.max_output_tokens,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=0,
                active_milliseconds=60000,
                wall_milliseconds=120000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd=str(request.cost_usd) if hasattr(request, 'cost_usd') and request.cost_usd else "0.00",
            expected_revision=current.revision,
            idempotency_key=f"model-{request.request_id}",
        )

        decision = check_reservation(current, reservation_request, now)
        if not decision.granted:
            raise ValueError(f"model reservation denied: {decision.reason}")

        reservation_id = str(uuid4())
        self._ops.create_model_reservation(
            reservation_id=reservation_id,
            invocation_id=str(request.invocation_id),
            max_input_tokens=request.max_input_tokens,
            max_output_tokens=request.max_output_tokens,
            cost_usd=str(request.cost_usd) if hasattr(request, 'cost_usd') and request.cost_usd else "0.00",
            expires_at=now.utc_timestamp,
        )

        return ModelReservation(
            reservation_id=reservation_id,
            scope=fence.scope,
            request_id=request.request_id,
            invocation_id=request.invocation_id,
            role=request.role,
            max_input_tokens=request.max_input_tokens,
            max_output_tokens=request.max_output_tokens,
            cost_usd=str(request.cost_usd) if hasattr(request, 'cost_usd') and request.cost_usd else "0.00",
            admitted_at=now.utc_timestamp,
            expires_at=now.utc_timestamp,
        )

    def publish_evidence(self, candidate, fence: OwnerFence):
        """Publish evidence candidate."""
        # Implementation would store evidence and return EvidenceRef
        raise NotImplementedError("T05: publish_evidence not yet implemented")

    def commit_preparation(self, candidate, fence: OwnerFence):
        """Commit dataset preparation."""
        raise NotImplementedError("T05: commit_preparation not yet implemented")

    def reserve_review(self, request: ReviewInput, fence: OwnerFence) -> ReviewReservation:
        """Reserve review pass."""
        now = ClockReading(
            utc_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            monotonic_milliseconds=0,
            process_id=str(uuid4()),
            trusted=True,
        )
        current = create_initial_budget(fence.scope)

        # Convert ReviewInput to ReservationRequest
        reservation_request = ReservationRequest(
            request_id=request.request.review_id,
            scope=fence.scope,
            purpose="review",
            counters=CounterAmounts(
                physical_requests=1,
                logical_invocations=1,
                input_tokens=10000,
                output_tokens=5000,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=1,  # One review pass
                active_milliseconds=60000,
                wall_milliseconds=120000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd="0.05",
            expected_revision=current.revision,
            idempotency_key=f"review-{request.request.review_id}",
        )

        decision = check_reservation(current, reservation_request, now)
        if not decision.granted:
            raise ValueError(f"review reservation denied: {decision.reason}")

        reservation_id = str(uuid4())
        review_id = str(uuid4())
        self._ops.create_review_reservation(
            reservation_id=reservation_id,
            review_id=review_id,
            max_physical_requests=1,
            max_input_tokens=10000,
            max_output_tokens=5000,
            cost_usd="0.05",
            deadline=now.utc_timestamp,
        )

        return ReviewReservation(
            reservation_id=reservation_id,
            scope=fence.scope,
            request=request,
            review_input_packet_hash=str(uuid4()),
            fence=fence,
            budget_reservation_id=str(uuid4()),
            reserved_at=now.utc_timestamp,
            deadline=now.utc_timestamp,
            max_physical_requests=1,
            max_input_tokens=10000,
            max_output_tokens=5000,
            cost_usd="0.05",
        )

    def accept_reply(self, reply: LinkedReply, fence: OwnerFence) -> ResumeReceipt:
        """Accept analytical reply."""
        resume_id = str(uuid4())
        self._ops.record_resume_receipt(
            resume_id=resume_id,
            run_id=reply.run_id,
            question_id=reply.question_id,
            reply_id=reply.reply_id,
            entry_intake_id=reply.entry_intake_id,
            run_revision=1,
            owner_generation=1,
            original_deadline="2099-12-31T23:59:59.999999Z",
            scope_json=fence.scope.model_dump_json(),
        )

        return ResumeReceipt(
            resume_id=resume_id,
            run_id=reply.run_id,
            question_id=reply.question_id,
            reply_id=reply.reply_id,
            entry_intake_id=reply.entry_intake_id,
            run_revision=1,
            owner_generation=1,
            accepted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            original_deadline="2099-12-31T23:59:59.999999Z",
            scope=fence.scope,
        )

    def finalize(self, candidate: FinalCandidate, fence: OwnerFence) -> FinalResult:
        """Finalize answer."""
        raise NotImplementedError("T05: finalize not yet implemented")

    def delete_dataset(self, dataset_id: UUID, scope: Scope) -> DeletionReceipt:
        """Delete dataset."""
        raise NotImplementedError("T05: delete_dataset not yet implemented")

    # --- Additional authority methods ---

    def accept_model(self, reservation_id: UUID, completion: ModelCompletion, fence: OwnerFence):
        """Accept model completion."""
        raise NotImplementedError("T05: accept_model not yet implemented")

    def record_operation(self, request: OperationRequest, fence: OwnerFence) -> UUID:
        """Record operation."""
        raise NotImplementedError("T05: record_operation not yet implemented")

    def record_retirement(self, proof, fence: OwnerFence):
        """Record retirement proof."""
        raise NotImplementedError("T05: record_retirement not yet implemented")

    def register_outcome(self, action_id: UUID, outcome, fence: OwnerFence) -> UUID:
        """Register action outcome."""
        raise NotImplementedError("T05: register_outcome not yet implemented")

    # --- Read/projection methods ---

    def read_projection(self, run_id: UUID, scope: Scope):
        """Read run projection."""
        raise NotImplementedError("T05: read_projection not yet implemented")

    def reserve_dispatch(self, task_id: UUID, fence: OwnerFence):
        """Reserve task dispatch."""
        raise NotImplementedError("T05: reserve_dispatch not yet implemented")

    def commit_wait(self, action_id: UUID, outcome, fence: OwnerFence) -> UUID:
        """Commit clarification wait outcome."""
        raise NotImplementedError("T05: commit_wait not yet implemented")

    def commit_review(self, review_id: UUID, assessment, fence: OwnerFence) -> UUID:
        """Commit review assessment."""
        raise NotImplementedError("T05: commit_review not yet implemented")