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
    # Convert UUID to canonical string format for CanonicalUUID fields
    run_id_str = str(run_state.run_id)
    chat_id_str = str(run_state.chat_id)
    return ConversationSnapshot(
        snapshot_id=run_id_str,
        chat_id=chat_id_str,
        cutoff_sequence=0,
        original_message={
            "message_id": run_id_str,
            "chat_id": chat_id_str,
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
    env_manifest_id_str = str(environment_manifest_id)
    active_op_id_str = str(active_operation_id) if active_operation_id else None
    return RuntimeControls(
        fence=run_state.fence,
        budget=run_state.budget,
        deadline=run_state.deadline,
        environment_manifest_id=env_manifest_id_str,
        environment_version="1.0",
        policy_version=policy_version,
        phase=phase,
        active_operation_id=active_op_id_str,
    )


def _build_packet_metadata(
    base_snapshot_id: str,
    policy_version: str,
    configuration_hash: str,
    selected_records: list[RecordSelection] | None = None,
    dependencies: list[dict] | None = None,
    coverage: list[CoverageNotice] | None = None,
) -> PacketMetadata:
    """Build packet metadata."""
    content = {
        "base_snapshot_id": base_snapshot_id,
        "selected_records": selected_records or [],
        "dependencies": dependencies or [],
        "coverage": coverage or [],
    }
    return PacketMetadata(
        packet_id=str(uuid4()),
        content_hash=_canonical_hash(content),
        policy_version=policy_version,
        configuration_hash=configuration_hash,
        base_snapshot_id=base_snapshot_id,
        selected_records=selected_records or [],
        dependencies=dependencies or [],
        coverage=coverage or [],
    )


def _extract_dependencies(
    evidence_list: list[TabularEvidence | EvidenceRegistryEntry],
    chart_list: list[ChartArtifact | EvidenceRegistryEntry] | None = None,
) -> list[dict]:
    """Extract source dependencies from evidence and charts.

    Handles both full evidence objects (TabularEvidence, ChartArtifact)
    and registry entries (EvidenceRegistryEntry) which only have dataset UUIDs.
    """
    deps = []
    for item in evidence_list:
        # Handle full TabularEvidence with SourceDependency objects
        if hasattr(item, 'dependencies') and item.dependencies:
            for dep in item.dependencies:
                deps.append({"dataset_id": str(dep.dataset_id), "snapshot_id": str(dep.snapshot_id)})
        # Handle EvidenceRegistryEntry with source_dependencies (list of UUIDs)
        elif hasattr(item, 'source_dependencies') and item.source_dependencies:
            for dataset_uuid in item.source_dependencies:
                # Registry entries don't have snapshot_id, use a placeholder
                deps.append({"dataset_id": str(dataset_uuid), "snapshot_id": "00000000-0000-0000-0000-000000000000"})
    if chart_list:
        for item in chart_list:
            if hasattr(item, 'dependencies') and item.dependencies:
                for dep in item.dependencies:
                    deps.append({"dataset_id": str(dep.dataset_id), "snapshot_id": str(dep.snapshot_id)})
            elif hasattr(item, 'source_dependencies') and item.source_dependencies:
                for dataset_uuid in item.source_dependencies:
                    deps.append({"dataset_id": str(dataset_uuid), "snapshot_id": "00000000-0000-0000-0000-000000000000"})
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
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
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
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
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
    artifact_store: Any = None,
) -> PythonInput:
    """Build PythonInput packet from run state and action."""
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "analysis", environment_manifest_id, policy_version)

    evidence_ids = [UUID(eid) for eid in action.input_evidence_ids]
    authorized_evidence = []
    for eid in evidence_ids:
        entry = run_state.get_evidence_by_id(eid)
        if entry and entry.evidence_type == "tabular":
            # Reconstruct TabularEvidence from artifact store if available
            if artifact_store is not None:
                try:
                    from querivue_agent.contracts.artifacts import ArtifactRef
                    artifact_ref = ArtifactRef(
                        artifact_id=entry.artifact_ref,
                        storage_ref=entry.artifact_ref,
                        media_type="application/vnd.apache.parquet",
                        size_bytes=0,
                        sha256=entry.integrity_hash,
                        environment_manifest_id=str(environment_manifest_id),
                    )
                    with artifact_store.read(artifact_ref, Scope()) as f:
                        import json
                        evidence_data = json.load(f)
                        from querivue_agent.contracts.evidence import TabularEvidence
                        authorized_evidence.append(TabularEvidence(**evidence_data))
                        continue
                except Exception:
                    pass
            # Fallback: create minimal TabularEvidence from registry entry
            from querivue_agent.contracts.evidence import (
                TabularEvidence, EvidenceColumn, TabularPreview, Int64Column, SQLProducer
            )
            from querivue_agent.contracts.artifacts import ArtifactRef, Sha256
            from querivue_agent.contracts.values import CanonicalUUID
            # Use schema from registry entry to create a basic column
            col_name = next(iter(entry.schema.keys())) if entry.schema else "col_0"
            col_type_str = entry.schema.get(col_name, "int64")
            fallback_column = EvidenceColumn(
                ordinal=0,
                name=col_name,
                original_label=col_name,
                original_ordinal=0,
                type=Int64Column(tag="int64"),
                nullable=True,
            )
            # Create a minimal ArtifactRef from the registry entry's artifact_ref
            fallback_artifact = ArtifactRef(
                artifact_id=entry.artifact_ref,
                storage_ref=entry.artifact_ref,
                media_type="application/vnd.apache.parquet",
                size_bytes=0,
                sha256=Sha256(entry.integrity_hash),
                environment_manifest_id=str(environment_manifest_id),
            )
            # Create a minimal SQLProducer for the fallback evidence
            fallback_producer = SQLProducer(
                kind="sql",
                run_id=CanonicalUUID(str(run_state.run_id)),
                action_id=CanonicalUUID(str(action.action_id)),
                operation_id=CanonicalUUID(str(uuid4())),
                attempt=1,
                sql="SELECT 1",
                parameters={},
                table_ids=[],
                input_evidence_ids=[],
                constraints=action.constraints,
                environment_manifest_id=CanonicalUUID(str(environment_manifest_id)),
                policy_version=policy_version,
            )
            authorized_evidence.append(TabularEvidence(
                evidence_id=str(entry.evidence_id),
                content_hash=entry.integrity_hash,
                artifact=fallback_artifact,
                columns=[fallback_column],
                row_count=entry.row_count,
                preview=TabularPreview(
                    columns=[fallback_column],
                    rows=[],
                    row_locators=[],
                    full_row_count=entry.row_count,
                    returned_row_count=0,
                    effective_limit=1,
                    ordering="unspecified",
                    truncated=True,
                    shortened_cells=[],
                ),
                producer=fallback_producer,
                dependencies=[{"dataset_id": str(dep), "snapshot_id": "00000000-0000-0000-0000-000000000000"} for dep in entry.source_dependencies],
            ))

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
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
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
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
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

    # Ensure we pass only the base Draft fields (not extra fields from subclasses)
    base_draft = Draft(
        blocks=draft.blocks,
        unmet_deliverables=draft.unmet_deliverables,
    )

    return ReviewInput(
        role="reviewer",
        packet=packet,
        scope=Scope(
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
        ),
        conversation=base_snapshot,
        controls=controls,
        request=review_request,
        draft=base_draft,
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
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
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
    base_snapshot = _build_base_snapshot(run_state)
    controls = _build_runtime_controls(run_state, "queued", environment_manifest_id, policy_version)

    submission_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
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