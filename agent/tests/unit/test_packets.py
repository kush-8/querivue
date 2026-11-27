"""Tests for packet building in context.py."""

import hashlib
from datetime import datetime, UTC
from uuid import UUID, uuid4

import pytest

from querivue_agent.context import (
    build_supervisor_input,
    build_sql_input,
    build_python_input,
    build_answer_input,
    build_review_input,
    build_clarification_input,
    build_entry_input,
)
from querivue_agent.contracts.inputs import (
    PacketMetadata,
    RuntimeControls,
    SQLAction,
    PythonAction,
    AnswerAction,
    ClarificationAction,
    ReviewRequest,
)
from querivue_agent.contracts.common import Scope, OwnerFence
from querivue_agent.contracts.budgets import (
    BudgetSnapshot,
    CounterSnapshot,
    BudgetCounters,
    MoneySnapshot,
)
from querivue_agent.contracts.records import Task, AdmissionReceipt
from querivue_agent.runtime.graph_state import RunState, create_initial_run_state, EvidenceRegistryEntry
from querivue_agent.contracts.evidence import TabularEvidence


def create_test_run_state(
    run_id: UUID | None = None,
    project_id: UUID | None = None,
    chat_id: UUID | None = None,
    question: str = "How many orders?",
    eligible_dataset_ids: list[UUID] | None = None,
) -> RunState:
    """Create a test RunState with minimal valid data."""
    run_id = run_id or uuid4()
    project_id = project_id or UUID("00000000-0000-4000-8000-000000000001")
    chat_id = chat_id or UUID("00000000-0000-4000-8000-000000000002")
    eligible_dataset_ids = eligible_dataset_ids or [UUID("00000000-0000-4000-8000-000000000003")]

    # Convert UUIDs to strings for CanonicalUUID fields
    run_id_str = str(run_id)
    project_id_str = str(project_id)
    chat_id_str = str(chat_id)
    eligible_dataset_ids_str = [str(uid) for uid in eligible_dataset_ids]
    receipt_id_str = str(uuid4())
    admission_id_str = str(uuid4())
    intake_id_str = str(uuid4())

    scope = Scope(
        project_id=project_id_str,
        chat_id=chat_id_str,
        run_id=run_id_str,
        eligible_dataset_ids=eligible_dataset_ids_str,
    )

    counters = {
        "physical_requests": CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
        "logical_invocations": CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
        "input_tokens": CounterSnapshot(limit=10000, used=0, reserved=0, unknown_reserved=0),
        "output_tokens": CounterSnapshot(limit=10000, used=0, reserved=0, unknown_reserved=0),
        "tool_calls": CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
        "query_executions": CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
        "dispatch_attempts": CounterSnapshot(limit=8, used=0, reserved=0, unknown_reserved=0),
        "active_milliseconds": CounterSnapshot(limit=600000, used=0, reserved=0, unknown_reserved=0),
        "wall_milliseconds": CounterSnapshot(limit=3600000, used=0, reserved=0, unknown_reserved=0),
        "output_bytes": CounterSnapshot(limit=134217728, used=0, reserved=0, unknown_reserved=0),
        "output_files": CounterSnapshot(limit=16, used=0, reserved=0, unknown_reserved=0),
    }

    budget_counters = BudgetCounters(**counters)
    money_snapshot = MoneySnapshot(
        limit="100.00",
        used="0.00",
        reserved="0.00",
        unknown_reserved="0.00",
        currency="USD",
    )

    budget = BudgetSnapshot(
        scope=scope,
        revision=0,
        counters=budget_counters,
        cost=money_snapshot,
        protected_reserves=[],
    )

    fence = OwnerFence(
        owner_id=chat_id_str,
        generation=1,
        scope=scope,
        subject_kind="run",
        subject_id=run_id_str,
        attempt=1,
        expected_revision=0,
        lease_expires_at="2099-12-31T23:59:59Z",
    )

    admission_receipt = AdmissionReceipt(
        receipt_id=receipt_id_str,
        admission_id=admission_id_str,
        intake_id=intake_id_str,
        run_id=run_id_str,
        scope=scope,
        cutoff_sequence=0,
        budget=budget,
        configuration_hash="0" * 64,
        accepted_at="2026-01-01T00:00:00Z",
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


def create_test_task(task_id: UUID | None = None) -> Task:
    """Create a test Task."""
    task_id = task_id or uuid4()
    action_id = uuid4()
    table_id = uuid4()
    action = SQLAction(
        type="sql",
        action_id=str(action_id),
        objective="Count orders",
        constraints={
            "metric_definitions": {},
            "filters": [],
            "date_windows": [],
            "analysis_timezone": None,
            "grain": None,
            "units": {},
        },
        table_ids=[str(table_id)],
        input_evidence_ids=[],
    )
    return Task(
        task_id=str(task_id),
        type="analysis",
        requires=[],
        actions=[action],
    )


class TestBuildSupervisorInput:
    def test_builds_supervisor_input_with_all_fields(self):
        run_state = create_test_run_state()
        pending_tasks = [create_test_task()]
        current_task = create_test_task()
        env_manifest_id = uuid4()

        result = build_supervisor_input(
            run_state=run_state,
            pending_tasks=pending_tasks,
            current_task=current_task,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            queue_revision=1,
            analysis_started=True,
        )

        assert result.role == "supervisor"
        assert isinstance(result.packet, PacketMetadata)
        assert result.packet.policy_version == "1.0"
        assert result.packet.configuration_hash == "0" * 64
        assert len(result.pending_tasks) == 1
        assert result.current_task is not None
        assert result.queue_revision == 1
        assert result.analysis_started is True
        assert isinstance(result.controls, RuntimeControls)
        assert result.controls.phase == "planning"

    def test_builds_supervisor_input_with_defaults(self):
        run_state = create_test_run_state()
        env_manifest_id = uuid4()

        result = build_supervisor_input(
            run_state=run_state,
            pending_tasks=[],
            current_task=None,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
        )

        assert result.queue_revision == 0
        assert result.analysis_started is False
        assert result.current_task is None


class TestBuildSQLInput:
    def test_builds_sql_input_with_action(self):
        run_state = create_test_run_state()
        task = create_test_task()
        action_id = uuid4()
        table_id = uuid4()
        action = SQLAction(
            type="sql",
            action_id=str(action_id),
            objective="Count orders",
            constraints={
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": "UTC",
                "grain": "day",
                "units": {},
            },
            table_ids=[str(table_id)],
            input_evidence_ids=[],
        )
        env_manifest_id = uuid4()
        # Create a table catalog to match the table_ids - requires all TableCatalog fields
        from querivue_agent.contracts.catalog import TableCatalog, ColumnCatalog, SourceDescriptor, FileSource
        from querivue_agent.contracts.catalog import ColumnImportSettings, TemporalBounds, TypedScalar, CandidateKey, TemporalKind
        from querivue_agent.contracts.values import CanonicalUUID
        from querivue_agent.contracts.evidence import Int64Column, TabularEvidence, EvidenceColumn, TabularPreview, SQLProducer, ArtifactRef, SourceDependency

        column_id = str(uuid4())
        table_catalog = TableCatalog(
            table_id=str(table_id),
            dataset_id=str(run_state.eligible_dataset_ids[0]),
            snapshot_id=str(uuid4()),
            ordinal=0,
            sql_name="orders",
            source=FileSource(kind="file", format="csv"),
            row_count=100,
            columns=[
                ColumnCatalog(
                    ordinal=0,
                    source_position=0,
                    column_id=column_id,
                    original_label="id",
                    sql_name="id",
                    type=Int64Column(tag="int64"),
                    nullable=False,
                    null_count=0,
                    settings=ColumnImportSettings(
                        source_position=0,
                        original_label="id",
                        requested_type=Int64Column(tag="int64"),
                        missing_markers=[],
                        decimal_separator=None,
                        thousands_separator=None,
                        datetime_format=None,
                        source_timezone=None,
                        conversion_choice=None,
                    ),
                    timezone_provenance_ref=None,
                    temporal_bounds=None,
                )
            ],
            warnings=[],
            profile_evidence_ids=[],
            candidate_keys=[
                CandidateKey(
                    column_ids=[column_id],
                    basis="source_schema",
                    verification_ref=None,
                )
            ],
        )
        tables = [table_catalog]
        table_profiles = []

        result = build_sql_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            tables=tables,
            table_profiles=table_profiles,
        )

        assert result.role == "sql"
        assert isinstance(result.packet, PacketMetadata)
        assert result.task_id == task.task_id
        assert result.attempt == 1
        assert result.request == action
        assert result.tables == tables
        assert result.evidence == []
        assert result.table_profiles == table_profiles
        assert result.controls.phase == "analysis"


class TestBuildPythonInput:
    def test_builds_python_input_with_action(self):
        run_state = create_test_run_state()
        task = create_test_task()
        action_id = uuid4()
        evidence_id = uuid4()
        action = PythonAction(
            type="python",
            action_id=str(action_id),
            objective="Analyze data",
            constraints={
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": "UTC",
                "grain": "day",
                "units": {},
            },
            input_evidence_ids=[str(evidence_id)],
            required_outputs=["evidence"],
        )
        env_manifest_id = uuid4()

        # Add mock evidence to run_state for the evidence_id
        # Need to create an EvidenceRegistryEntry (not TabularEvidence) since run_state.evidence expects EvidenceRegistryEntry
        from querivue_agent.contracts.evidence import (
            TabularEvidence, EvidenceColumn, TabularPreview, SQLProducer, SourceDependency, Int64Column
        )
        from querivue_agent.contracts.artifacts import ArtifactRef, Sha256
        from datetime import datetime, UTC

        mock_evidence = TabularEvidence(
            evidence_id=str(evidence_id),
            content_hash=Sha256("0" * 64),
            artifact=ArtifactRef(
                artifact_id=str(uuid4()),
                storage_ref=str(uuid4()),
                media_type="application/vnd.apache.parquet",
                size_bytes=1000,
                sha256=Sha256("0" * 64),
                environment_manifest_id=str(env_manifest_id),
            ),
            columns=[
                EvidenceColumn(
                    ordinal=0,
                    name="id",
                    original_label="id",
                    original_ordinal=0,
                    type=Int64Column(tag="int64"),
                    nullable=False,
                )
            ],
            row_count=100,
            preview=TabularPreview(
                columns=[
                    EvidenceColumn(
                        ordinal=0,
                        name="id",
                        original_label="id",
                        original_ordinal=0,
                        type=Int64Column(tag="int64"),
                        nullable=False,
                    )
                ],
                rows=[["1"]],
                row_locators=[0],
                full_row_count=100,
                returned_row_count=1,
                effective_limit=100,
                ordering="unspecified",
                truncated=True,
                shortened_cells=[],
            ),
            producer=SQLProducer(
                kind="sql",
                run_id=str(run_state.run_id),
                action_id=str(action_id),
                operation_id=str(uuid4()),
                attempt=1,
                sql="SELECT 1",
                parameters={},
                table_ids=[],
                input_evidence_ids=[],
                constraints=action.constraints,
                environment_manifest_id=str(env_manifest_id),
                policy_version="1.0",
            ),
            dependencies=[
                SourceDependency(
                    dataset_id=str(run_state.eligible_dataset_ids[0]),
                    snapshot_id=str(uuid4()),
                )
            ],
        )

        # Wrap in EvidenceRegistryEntry as expected by run_state.evidence
        registry_entry = EvidenceRegistryEntry(
            evidence_id=evidence_id,
            evidence_type="tabular",
            producer="sql",
            method="execute_query",
            schema={"id": "int64"},
            row_count=100,
            source_dependencies=[UUID(str(run_state.eligible_dataset_ids[0]))],
            integrity_hash="0" * 64,
            artifact_ref=str(mock_evidence.artifact.artifact_id),
            preview={"rows": 1, "columns": ["id"]},
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        # Store the TabularEvidence in a way the context.py can access it
        # The context.py code retrieves from run_state.evidence and checks entry.evidence_type
        run_state.evidence[str(evidence_id)] = registry_entry

        result = build_python_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
        )

        assert result.role == "python"
        assert isinstance(result.packet, PacketMetadata)
        assert result.task_id == task.task_id
        assert result.attempt == 1
        assert result.request == action
        # Now returns TabularEvidence objects
        assert len(result.evidence) == 1
        assert result.evidence[0].evidence_id == str(evidence_id)
        assert result.controls.phase == "analysis"


class TestBuildAnswerInput:
    def test_builds_answer_input_with_action(self):
        run_state = create_test_run_state()
        task = create_test_task()
        action_id = uuid4()
        action = AnswerAction(
            type="answer",
            action_id=str(action_id),
            objective="Answer question",
            constraints={
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": "UTC",
                "grain": "day",
                "units": {},
            },
            evidence_ids=[],
            chart_artifact_ids=[],
        )
        env_manifest_id = uuid4()
        obligations = []
        unmet_facts = []
        partial_authorization = None
        revision = None

        result = build_answer_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            obligations=obligations,
            unmet_facts=unmet_facts,
            partial_authorization=partial_authorization,
            revision=revision,
        )

        assert result.role == "answer"
        assert isinstance(result.packet, PacketMetadata)
        assert result.task_id == task.task_id
        assert result.attempt == 1
        assert result.request == action
        assert result.obligations == obligations
        assert result.unmet_facts == unmet_facts
        assert result.partial_authorization == partial_authorization
        assert result.revision == revision
        assert result.controls.phase == "answer"


class TestBuildReviewInput:
    def test_builds_review_input_with_draft(self):
        run_state = create_test_run_state()
        task = create_test_task()
        action_id = uuid4()
        draft_id = uuid4()
        action = AnswerAction(
            type="answer",
            action_id=str(action_id),
            objective="Answer question",
            constraints={
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": "UTC",
                "grain": "day",
                "units": {},
            },
            evidence_ids=[],
            chart_artifact_ids=[],
            draft_id=str(draft_id),
        )
        env_manifest_id = uuid4()

        from querivue_agent.contracts.content import Draft
        from querivue_agent.codec import canonical_bytes
        draft = Draft(
            blocks=[
                {"block_id": "answer", "kind": "general_explanation", "spans": [{"kind": "text", "text": "Answer"}], "supports": []}
            ],
            unmet_deliverables=[],
        )
        # Compute content_hash using canonical encoding
        content_hash = hashlib.sha256(canonical_bytes(draft.model_dump())).hexdigest()
        rendered_text = "Answer"

        # Build draft input first
        draft_input = build_answer_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            obligations=[],
            unmet_facts=[],
            partial_authorization=None,
            revision=None,
        )

        # Create a wrapper that has the extra fields context.py expects
        class DraftWithExtras(Draft):
            content_hash: str
            rendered_text: str

            class Config:
                extra = "allow"

        draft_with_extras = DraftWithExtras(
            blocks=draft.blocks,
            unmet_deliverables=draft.unmet_deliverables,
            content_hash=content_hash,
            rendered_text=rendered_text,
        )

        result = build_review_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            draft=draft_with_extras,
            draft_input=draft_input,
        )

        assert result.role == "reviewer"
        assert isinstance(result.packet, PacketMetadata)
        assert result.draft == draft
        assert result.draft_input == draft_input
        assert result.rendered_text == "Answer"
        assert result.controls.phase == "review"


class TestBuildClarificationInput:
    def test_builds_clarification_input_with_action(self):
        run_state = create_test_run_state()
        task = create_test_task()
        action_id = uuid4()
        action = ClarificationAction(
            type="clarify",
            action_id=str(action_id),
            issue="Which window?",
            candidate_interpretations=[],
            constraints={
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": "UTC",
                "grain": "day",
                "units": {},
            },
            input_evidence_ids=[],
            context_refs=[],
        )
        env_manifest_id = uuid4()
        source_choices = []

        result = build_clarification_input(
            run_state=run_state,
            task=task,
            action=action,
            attempt=1,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
            source_choices=source_choices,
        )

        assert result.role == "clarification"
        assert isinstance(result.packet, PacketMetadata)
        assert result.task_id == task.task_id
        assert result.attempt == 1
        assert result.request == action
        assert result.source_choices == source_choices
        assert result.controls.phase == "clarification"


class TestBuildEntryInput:
    def test_builds_entry_input(self):
        run_state = create_test_run_state()
        scope = Scope(
            project_id=str(run_state.project_id),
            chat_id=str(run_state.chat_id),
            run_id=str(run_state.run_id),
            eligible_dataset_ids=[str(uid) for uid in run_state.eligible_dataset_ids],
        )
        env_manifest_id = uuid4()

        result = build_entry_input(
            run_state=run_state,
            scope=scope,
            question="How many orders?",
            input_kind="new_question",
            linked_context=None,
            followup_context=[],
            cutoff_sequence=0,
            environment_manifest_id=env_manifest_id,
            policy_version="1.0",
            configuration_hash="0" * 64,
        )

        assert result.role == "entry"
        assert isinstance(result.packet, PacketMetadata)
        assert result.input_kind == "new_question"
        assert result.submission_text == "How many orders?"
        assert result.submission_hash == hashlib.sha256(b"How many orders?").hexdigest()
        assert result.policy_version == "1.0"
        assert result.cutoff_sequence == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])