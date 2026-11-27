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
from querivue_agent.contracts.catalog import PreparedCandidate
from querivue_agent.contracts.common import OwnerFence, Scope
from querivue_agent.contracts.entry import EntryInput as IntakeEntryInput
from querivue_agent.contracts.evidence import EvidenceCandidate, TabularEvidence
from querivue_agent.contracts.inputs import ReviewInput
from querivue_agent.contracts.responses import ReviewAssessment
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
    OperationOutcome,
    OperationRequest,
    QueueReceipt,
    ResumeReceipt,
    ReviewReservation,
)
from querivue_agent.contracts.evidence import EvidenceRef
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

    def publish_evidence(self, candidate: EvidenceCandidate, fence: OwnerFence) -> TabularEvidence:
        """Publish evidence candidate and return the published evidence."""
        evidence = candidate.evidence
        evidence_id = str(evidence.evidence_id)
        content_hash = evidence.content_hash
        artifact = evidence.artifact

        # Store the evidence artifact reference
        self._ops.store_payload(
            payload_id=evidence_id,
            family="evidence",
            version=1,
            canonical_bytes=evidence.model_dump_json().encode(),
            digest=content_hash,
        )

        # Add dependency to the payload
        for dep in evidence.dependencies:
            self._ops.add_dependency(evidence_id, str(dep.dataset_id), str(dep.snapshot_id))

        return evidence

    def commit_preparation(self, candidate: PreparedCandidate, fence: OwnerFence) -> None:
        """Commit dataset preparation."""
        snapshot = candidate.snapshot
        snapshot_id = str(snapshot.snapshot_id)
        dataset_id = str(snapshot.dataset_id)
        prepared_ref = snapshot.prepared_ref
        prepared_hash = snapshot.prepared_hash
        publication_ref = snapshot.publication_ref

        # Update the dataset snapshot with prepared references
        self._ops.update_snapshot_prepared(
            snapshot_id=snapshot_id,
            prepared_ref=prepared_ref,
            prepared_hash=prepared_hash,
            publication_ref=publication_ref,
        )

        # Update dataset status to validated
        self._ops.update_dataset_status(
            dataset_id=dataset_id,
            status="validated",
            settings_hash=str(snapshot.settings_hash),
            environment_manifest_id=str(snapshot.environment_manifest_id),
        )

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
        run_id = str(fence.scope.run_id)
        result_id = str(uuid4())
        candidate_id = str(candidate.candidate_id)
        content_hash = candidate.content_hash
        completeness = candidate.completeness
        rendered_text = candidate.rendered_text
        rendering_policy_version = candidate.rendering_policy_version
        dependencies = candidate.dependencies

        # Determine route and review status
        if candidate.kind == "reviewed":
            route = "reviewed"
            review_status = "approved"
            # Get evidence and chart IDs from the draft/review
            evidence_ids = []
            chart_artifact_ids = []
            # In a real implementation, these would come from the draft
        else:
            route = "direct"
            review_status = "not_required_direct"
            evidence_ids = []
            chart_artifact_ids = []

        # Record final result
        self._ops.record_final_result(
            result_id=result_id,
            run_id=run_id,
            route=route,
            candidate_id=candidate_id,
            content_hash=content_hash,
            completeness=completeness,
            rendered_text=rendered_text,
            rendering_policy_version=rendering_policy_version,
            evidence_ids=evidence_ids,
            chart_artifact_ids=chart_artifact_ids,
            dependencies_json=json.dumps([d.model_dump() for d in dependencies]),
            review_status=review_status,
        )

        return FinalResult(
            kind="answer",
            result_id=result_id,
            scope=fence.scope,
            route=route,
            candidate_id=candidate_id,
            content_hash=content_hash,
            completeness=completeness,
            rendered_text=rendered_text,
            rendering_policy_version=rendering_policy_version,
            evidence_ids=evidence_ids,
            chart_artifact_ids=chart_artifact_ids,
            dependencies=dependencies,
            published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            review_status=review_status,
        )

    def delete_dataset(self, dataset_id: UUID, scope: Scope) -> DeletionReceipt:
        """Delete dataset."""
        deletion_id = str(uuid4())
        dataset_id_str = str(dataset_id)
        project_id = scope.project_id

        # Get the dataset to verify it exists
        dataset = self._ops.get_dataset(dataset_id_str)
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id_str} not found")

        # Update dataset status to deleted
        self._ops.update_dataset_status(dataset_id_str, "deleted")

        # In a real implementation, these would be populated from actual dependencies
        invalidated_run_ids: list[str] = []
        removed_result_ids: list[str] = []
        deferred_artifact_ids: list[str] = []
        retirement_pending_incarnation_ids: list[str] = []
        tombstone_revision = 1

        # Record deletion receipt
        self._ops.record_deletion_receipt(
            deletion_id=deletion_id,
            project_id=project_id,
            dataset_id=dataset_id_str,
            tombstone_revision=tombstone_revision,
            invalidated_run_ids=invalidated_run_ids,
            removed_result_ids=removed_result_ids,
            deferred_artifact_ids=deferred_artifact_ids,
            retirement_pending_incarnation_ids=retirement_pending_incarnation_ids,
        )

        return DeletionReceipt(
            deletion_id=deletion_id,
            project_id=project_id,
            dataset_id=dataset_id,
            tombstone_revision=tombstone_revision,
            invalidated_run_ids=invalidated_run_ids,
            removed_result_ids=removed_result_ids,
            deferred_artifact_ids=deferred_artifact_ids,
            retirement_pending_incarnation_ids=retirement_pending_incarnation_ids,
            committed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    # --- Additional authority methods ---

    def accept_model(self, reservation_id: UUID, completion: ModelCompletion, fence: OwnerFence) -> None:
        """Accept model completion."""
        # Record the model completion
        self._ops.record_model_completion(
            completion_id=str(completion.completion_id),
            reservation_id=str(reservation_id),
            request_hash=completion.request_hash,
            status=completion.status,
            response_ref=str(completion.response_artifact.artifact_id) if completion.response_artifact else None,
            provider_request_id=completion.provider_request_id,
            observed_model_revision=completion.observed_model_revision,
            stop_reason=completion.stop_reason,
            usage_json=completion.usage.model_dump_json(),
            error_ref=str(completion.error_ref) if completion.error_ref else None,
        )

        # Complete the invocation
        self._ops.complete_invocation(
            invocation_id=str(completion.invocation_id),
            status="completed" if completion.status == "completed" else "failed",
            completion_json=completion.model_dump_json() if completion.status == "completed" else None,
        )

    def record_operation(self, request: OperationRequest, fence: OwnerFence) -> UUID:
        """Record operation."""
        operation_id = request.operation_id
        operation_id_str = str(operation_id)

        # Create the operation record
        self._ops.create_operation(
            operation_id=operation_id_str,
            run_id=str(fence.scope.run_id) if fence.scope.run_id else None,
            task_id=str(request.task_id) if request.task_id else None,
            action_id=str(request.action_id) if request.action_id else None,
            attempt=request.attempt,
            execution_generation=request.execution_generation,
            invocation_key=request.invocation_key,
            request_hash=request.request_hash,
            kind=request.kind,
            request_json=request.request.model_dump_json(),
            input_artifacts_json=json.dumps([a.model_dump() for a in request.input_artifacts]),
            deadline=request.deadline,
            environment_manifest_id=str(request.environment_manifest_id),
        )

        return operation_id

    def record_retirement(self, proof: RetirementProof, fence: OwnerFence) -> None:
        """Record retirement proof."""
        self._ops.record_retirement_proof(
            retirement_id=str(proof.retirement_id),
            sandbox_id=proof.sandbox_id,
            incarnation_id=str(proof.incarnation_id),
            method=proof.method,
            proof_ref=str(proof.proof_ref),
            environment_manifest_id=str(proof.environment_manifest_id),
        )

    def register_outcome(self, action_id: UUID, outcome: OperationOutcome, fence: OwnerFence) -> UUID:
        """Register action outcome."""
        outcome_id = uuid4()
        outcome_id_str = str(outcome_id)
        action_id_str = str(action_id)
        run_id_str = str(fence.scope.run_id)

        # Record the operation outcome
        self._ops.record_operation_outcome(
            outcome_id=outcome_id_str,
            operation_id=action_id_str,  # Using action_id as operation_id for now
            attempt=outcome.attempt,
            execution_generation=outcome.execution_generation,
            request_hash=outcome.request_hash,
            status=outcome.status,
            evidence_json=json.dumps([e.model_dump() for e in outcome.evidence]),
            charts_json=json.dumps([c.model_dump() for c in outcome.charts]),
            diagnostics_json=outcome.diagnostics.model_dump_json(),
        )

        # Update action status based on outcome
        if outcome.status == "succeeded":
            self._ops.update_action_status(action_id_str, "completed")
        elif outcome.status == "failed":
            self._ops.update_action_status(action_id_str, "failed")
        elif outcome.status == "blocked":
            self._ops.update_action_status(action_id_str, "blocked")

        return outcome_id

    # --- Read/projection methods ---

    def read_projection(self, run_id: UUID, scope: Scope) -> GraphProjection:
        """Read run projection for graph execution."""
        from querivue_agent.contracts.state import GraphProjection, RunState, RunExecutionStatus
        from querivue_agent.contracts.evidence import TabularEvidence
        from querivue_agent.contracts.budgets import BudgetSnapshot
        from querivue_agent.contracts.inputs import RunInput, SupervisorInput
        from querivue_agent.contracts.common import OwnerFence
        from querivue_agent.contracts.values import CanonicalUUID
        from querivue_agent.contracts.budgets import create_initial_budget

        run_id_str = str(run_id)

        # Get run from ledger
        run = self._ops.get_run(run_id_str)
        if run is None:
            raise ValueError(f"Run {run_id_str} not found")

        # Build a minimal RunState from stored data
        # In a real implementation, this would reconstruct full state from ledger
        budget = create_initial_budget(scope)

        execution_status = RunExecutionStatus(
            phase="queued",
            fence=OwnerFence(
                scope=scope,
                subject_kind="run",
                subject_id=run_id,
                owner_id=run.get("owner_id", ""),
                generation=run.get("generation", 1),
                attempt=1,
                expected_revision=run.get("run_revision", 1),
                lease_expires_at="2099-12-31T23:59:59.999999Z",
            ),
            budget=budget,
            deadline=run.get("deadline", "2099-12-31T23:59:59.999999Z"),
            run_revision=run.get("run_revision", 1),
            queue_revision=run.get("queue_revision", 0),
            expected_attempts={},
            active_draft_ref=None,
            active_review_ref=None,
            active_question_ref=None,
            analysis_started=False,
            review_reservations=[],
        )

        run_state = RunState(
            input=RunInput(
                run_id=run_id,
                project_id=scope.project_id,
                chat_id=scope.chat_id,
                eligible_dataset_ids=scope.eligible_dataset_ids,
                question=run.get("question", ""),
            ),
            context=SupervisorInput(
                scope=scope,
                conversation=None,  # Would be loaded from ledger
                plan=None,  # Would be loaded from ledger
                inbox=[],
            ),
            evidence={},
            messages=[],
            pending_tasks=[],
            current_task=None,
            outcomes={},
            execution_status=execution_status,
            output=None,
        )

        return GraphProjection(
            schema_version="1.0",
            graph_version="1.0",
            run_id=CanonicalUUID(run_id_str),
            thread_id=CanonicalUUID(run_id_str),
            run_revision=run.get("run_revision", 1),
            state=run_state,
            serialized_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            configuration_hash=run.get("configuration_hash", "0" * 64),
            namespace="default",
        )

    def reserve_dispatch(self, task_id: UUID, fence: OwnerFence) -> str:
        """Reserve task dispatch budget."""
        from querivue_agent.contracts.budgets import (
            ClockReading,
            ReservationRequest,
            CounterAmounts,
        )
        from querivue_agent.runtime.budgets import check_reservation, create_initial_budget

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

        current = create_initial_budget(fence.scope)

        reservation_request = ReservationRequest(
            request_id=str(task_id),
            scope=fence.scope,
            purpose="dispatch",
            counters=CounterAmounts(
                physical_requests=1,
                logical_invocations=1,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=1,
                active_milliseconds=30000,
                wall_milliseconds=60000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd="0.00",
            expected_revision=current.revision,
            idempotency_key=f"dispatch-{task_id}",
        )

        decision = check_reservation(current, reservation_request, now)
        if not decision.granted:
            raise ValueError(f"dispatch reservation denied: {decision.reason}")

        # Record the dispatch reservation
        reservation_id = str(uuid4())
        self._ops.create_task(str(task_id), str(fence.scope.run_id), '{"status": "dispatched"}')
        self._ops.update_task_status(str(task_id), "dispatched")

        return reservation_id

    def commit_wait(self, action_id: UUID, outcome: OperationOutcome, fence: OwnerFence) -> UUID:
        """Commit clarification wait outcome."""
        outcome_id = uuid4()
        outcome_id_str = str(outcome_id)
        action_id_str = str(action_id)
        run_id_str = str(fence.scope.run_id)

        # Record the operation outcome
        self._ops.record_operation_outcome(
            outcome_id=outcome_id_str,
            operation_id=action_id_str,
            attempt=outcome.attempt,
            execution_generation=outcome.execution_generation,
            request_hash=outcome.request_hash,
            status=outcome.status,
            evidence_json=json.dumps([e.model_dump() for e in outcome.evidence]),
            charts_json=json.dumps([c.model_dump() for c in outcome.charts]),
            diagnostics_json=outcome.diagnostics.model_dump_json(),
        )

        # Update action status based on outcome
        if outcome.status == "succeeded":
            self._ops.update_action_status(action_id_str, "completed")
        elif outcome.status == "failed":
            self._ops.update_action_status(action_id_str, "failed")
        elif outcome.status == "blocked":
            self._ops.update_action_status(action_id_str, "blocked")

        # Also record as a regular outcome for tracking
        self._ops.record_outcome(
            outcome_id=outcome_id_str,
            action_id=action_id_str,
            run_id=run_id_str,
            attempt=outcome.attempt,
            execution_generation=outcome.execution_generation,
            outcome_json=outcome.model_dump_json(),
        )

        return outcome_id

    def commit_review(self, review_id: UUID, assessment: ReviewAssessment, fence: OwnerFence) -> UUID:
        """Commit review assessment."""
        review_id_str = str(review_id)
        run_id_str = str(fence.scope.run_id)

        # Record the review in the ledger
        self._ops.create_review(
            review_id=review_id_str,
            run_id=run_id_str,
            draft_id=str(assessment.draft_id) if hasattr(assessment, 'draft_id') else "00000000-0000-0000-0000-000000000000",
            review_pass=assessment.review_pass if hasattr(assessment, 'review_pass') else 1,
            assessment_json=assessment.model_dump_json(),
            verdict="approved" if hasattr(assessment, 'verdict') and assessment.verdict == "approved" else "rejected",
            draft_content_hash=str(assessment.draft_content_hash) if hasattr(assessment, 'draft_content_hash') else "0" * 64,
            draft_input_packet_hash=str(assessment.draft_input_packet_hash) if hasattr(assessment, 'draft_input_packet_hash') else "0" * 64,
            rendering_policy_version=assessment.rendering_policy_version if hasattr(assessment, 'rendering_policy_version') else "1.0",
            deadline="2099-12-31T23:59:59.999999Z",
        )

        return review_id