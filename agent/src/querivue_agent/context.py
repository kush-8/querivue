"""Context packet construction for specialist inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from typing import Any
from uuid import UUID, uuid4

from querivue_agent.contracts.budgets import BudgetSnapshot
from querivue_agent.contracts.common import Scope, OwnerFence, Hash64
from querivue_agent.contracts.inputs import (
    PacketMetadata,
    ConversationSnapshot,
    RuntimeControls,
    RecordSelection,
    CoverageNotice,
    SupervisorInput,
    SQLInput,
    PythonInput,
    AnswerInput,
    ReviewInput,
    ClarificationInput,
    EntryInput as RoleEntryInput,
)
from querivue_agent.contracts.records import (
    AdmissionReceipt,
    Task,
)
from querivue_agent.runtime.graph_state import ActionOutcome
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.contracts.catalog import TableCatalog
from querivue_agent.runtime.graph_state import RunState, EvidenceRegistryEntry
from querivue_agent.contracts.actions import SQLAction, PythonAction, AnswerAction, ClarificationAction
from querivue_agent.contracts.content import Draft


def _canonical_hash(obj: Any) -> Hash64:
    """Compute canonical SHA-256 hash of an object."""
    canonical = json.dumps(obj, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _build_base_snapshot(run_state: RunState) -> ConversationSnapshot:
    """Build base conversation snapshot from run state."""
    return ConversationSnapshot(
        snapshot_id=run_state.run_id,
        chat_id=run_state.chat_id,
        cutoff_sequence=0,
        original_message={
            "message_id": run_state.run_id,
            "chat_id": run_state.chat_id,
            "sequence": 0,
            "text": run_state.question,
            "content_hash": _canonical_hash(run_state.question),
        },
        linked_replies=[],
        context_records=[],
        interpretation_records=[],
        thread_index=[],
        conflicts=[],
    )


def _build_runtime_controls(
    run_state: RunState,
    phase: str,
    environment_manifest_id: UUID,
    policy_version: str,
    active_operation_id: UUID | None = None,
) -> RuntimeControls:
    """Build runtime controls for a packet."""
    return RuntimeControls(
        fence=run_state.fence,
        budget=run_state.budget,
        deadline=run_state.deadline,
        environment_manifest_id=environment_manifest_id,
        environment_version="1.0",
        policy_version=policy_version,
        phase=phase,
        active_operation_id=active_operation_id,
    )


def _build_packet_metadata(
    base_snapshot_id: UUID,
    policy_version: str,
    configuration_hash: str,
    selected_records: list[RecordSelection] | None = None,
    dependencies: list[dict] | None = None,
    coverage: list[CoverageNotice] | None = None,
) -> PacketMetadata:
    """Build packet metadata."""
    content = {
        "base_snapshot_id": str(base_snapshot_id),
        "selected_records": selected_records or [],
        "dependencies": dependencies or [],
        "coverage": coverage or [],
    }
    return PacketMetadata(
        packet_id=uuid4(),
        content_hash=_canonical_hash(content),
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        base_snapshot_id=base_snapshot_id,
        selected_records=selected_records or [],
        dependencies=dependencies or [],
        coverage=coverage or [],
    )


def _extract_dependencies(
    evidence_list: list[TabularEvidence],
    chart_list: list[ChartArtifact] | None = None,
) -> list[dict]:
    """Extract source dependencies from evidence and charts."""
    deps = []
    for item in evidence_list:
        for dep in item.dependencies:
            deps.append({"dataset_id": str(dep.dataset_id), "snapshot_id": str(dep.snapshot_id)})
    if chart_list:
        for item in chart_list:
            for dep in item.dependencies:
                deps.append({"dataset_id": str(dep.dataset_id), "snapshot_id": str(dep.snapshot_id)})
    return deps


def build_supervisor_input(
    run_state: RunState,
    pending_tasks: list[Task],
    current_task: Task | None,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    queue_revision: int = 0,
    analysis_started: bool = False,
) -> SupervisorInput:
    """Build SupervisorInput packet from run state."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "planning", environment_manifest_id, policy_version)

    # Collect evidence from registry
    evidence = [entry for entry in run_state.evidence.values() if entry.evidence_type == "tabular"]
    charts = [entry for entry in run_state.evidence.values() if entry.evidence_type == "chart"]

    dependencies = _extract_dependencies(evidence, charts)

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    return SupervisorInput(
        role="supervisor",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        pending_tasks=pending_tasks,
        current_task=current_task,
        outcomes=[run_state.get_outcome_by_action(outcome.action_id) for outcome in run_state.outcomes.values()],
        evidence=evidence,
        charts=charts,
        catalog=[],
        obligations=[],
        gaps=[],
        source_choices=[],
        queue_revision=queue_revision,
        analysis_started=analysis_started,
    )


def build_sql_input(
    run_state: RunState,
    task: Task,
    action: SQLAction,
    attempt: int,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    tables: list[TableCatalog],
    table_profiles: list[TabularEvidence],
) -> SQLInput:
    """Build SQLInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "analysis", environment_manifest_id, policy_version)

    # Gather authorized evidence
    evidence_ids = [UUID(eid) for eid in action.input_evidence_ids]
    authorized_evidence = []
    for eid in evidence_ids:
        entry = run_state.get_evidence_by_id(eid)
        if entry and entry.evidence_type == "tabular":
            # Reconstruct TabularEvidence from registry
            authorized_evidence.append(entry)

    dependencies = _extract_dependencies(authorized_evidence, None)
    for table in tables:
        dependencies.append({"dataset_id": str(table.dataset_id), "snapshot_id": str(table.snapshot_id)})

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    return SQLInput(
        role="sql",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        task_id=task.task_id,
        attempt=attempt,
        request=action,
        tables=tables,
        evidence=authorized_evidence,
        table_profiles=table_profiles,
    )


def build_python_input(
    run_state: RunState,
    task: Task,
    action: PythonAction,
    attempt: int,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
) -> PythonInput:
    """Build PythonInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "analysis", environment_manifest_id, policy_version)

    evidence_ids = [UUID(eid) for eid in action.input_evidence_ids]
    authorized_evidence = []
    for eid in evidence_ids:
        entry = run_state.get_evidence_by_id(eid)
        if entry and entry.evidence_type == "tabular":
            authorized_evidence.append(entry)

    dependencies = _extract_dependencies(authorized_evidence, None)

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    return PythonInput(
        role="python",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        task_id=task.task_id,
        attempt=attempt,
        request=action,
        evidence=authorized_evidence,
    )


def build_answer_input(
    run_state: RunState,
    task: Task,
    action: AnswerAction,
    attempt: int,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    obligations: list,
    unmet_facts: list,
    partial_authorization: dict | None,
    revision: dict | None,
) -> AnswerInput:
    """Build AnswerInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "answer", environment_manifest_id, policy_version)

    # Gather all evidence from outcomes
    evidence = []
    charts = []
    for outcome in run_state.outcomes.values():
        for eid in outcome.evidence_ids:
            entry = run_state.get_evidence_by_id(eid)
            if entry:
                if entry.evidence_type == "tabular":
                    evidence.append(entry)
                elif entry.evidence_type == "chart":
                    charts.append(entry)

    dependencies = _extract_dependencies(evidence, charts)

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    return AnswerInput(
        role="answer",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        task_id=task.task_id,
        attempt=attempt,
        request=action,
        evidence=evidence,
        charts=charts,
        obligations=obligations,
        unmet_facts=unmet_facts,
        partial_authorization=partial_authorization,
        revision=revision,
    )


def build_review_input(
    run_state: RunState,
    task: Task,
    action: AnswerAction,
    attempt: int,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    draft: Draft,
    draft_input: AnswerInput,
) -> ReviewInput:
    """Build ReviewInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "review", environment_manifest_id, policy_version)

    # Use the same evidence as the draft input
    evidence = draft_input.evidence
    charts = draft_input.charts
    dependencies = _extract_dependencies(evidence, charts)

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    # Build review request
    from querivue_agent.contracts.inputs import ReviewRequest
    review_request = ReviewRequest(
        review_id=action.draft_id,
        draft_id=action.draft_id,
        draft_content_hash=draft.content_hash,
        draft_input_packet_hash=draft_input.packet.content_hash,
        rendering_policy_version=policy_version,
        review_pass=1,
    )

    return ReviewInput(
        role="reviewer",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        request=review_request,
        draft=draft,
        rendered_text=draft.rendered_text,
        draft_input=draft_input,
        review_input_packet_hash=packet.content_hash,
    )


def build_clarification_input(
    run_state: RunState,
    task: Task,
    action: ClarificationAction,
    attempt: int,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
    source_choices: list,
) -> ClarificationInput:
    """Build ClarificationInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "clarification", environment_manifest_id, policy_version)

    evidence = []
    for eid in action.input_evidence_ids:
        entry = run_state.get_evidence_by_id(UUID(eid))
        if entry and entry.evidence_type == "tabular":
            evidence.append(entry)

    dependencies = _extract_dependencies(evidence, None)
    for choice in source_choices:
        dependencies.append({"dataset_id": str(choice.dataset_id), "snapshot_id": str(choice.snapshot_id)})

    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        dependencies=dependencies,
    )

    return ClarificationInput(
        role="clarification",
        packet=packet,
        scope=Scope(
            project_id=run_state.project_id,
            chat_id=run_state.chat_id,
            run_id=run_state.run_id,
            eligible_dataset_ids=run_state.eligible_dataset_ids,
        ),
        conversation=base_snapshot,
        controls=controls,
        task_id=task.task_id,
        attempt=attempt,
        request=action,
        evidence=evidence,
        obligations=[],
        source_choices=source_choices,
    )


def build_entry_input(
    run_state: RunState,
    scope: Scope,
    question: str,
    input_kind: str,
    linked_context: dict | None,
    followup_context: list,
    cutoff_sequence: int | None,
    environment_manifest_id: UUID,
    policy_version: str,
    configuration_hash: str,
) -> RoleEntryInput:
    """Build EntryInput packet for intake assessment."""
    base_snapshot = ConversationSnapshot(
        snapshot_id=run_state.run_id,
        chat_id=run_state.chat_id,
        cutoff_sequence=cutoff_sequence or 0,
        original_message={
            "message_id": run_state.run_id,
            "chat_id": run_state.chat_id,
            "sequence": 0,
            "text": question,
            "content_hash": _canonical_hash(question),
        },
        linked_replies=[],
        context_records=[],
        interpretation_records=[],
        thread_index=[],
        conflicts=[],
    )
    controls = _build_runtime_controls(run_state, "admitted", environment_manifest_id, policy_version)

    submission_hash = _canonical_hash(question)
    packet = _build_packet_metadata(
        base_snapshot_id=base_snapshot.snapshot_id,
        policy_version=policy_version,
        configuration_hash=configuration_hash,
    )

    return RoleEntryInput(
        role="entry",
        packet=packet,
        scope=scope,
        input_kind=input_kind,
        submission_text=question,
        submission_hash=submission_hash,
        policy_version=policy_version,
        linked_context=linked_context,
        followup_context=followup_context,
        cutoff_sequence=cutoff_sequence,
    )