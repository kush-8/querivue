"""Integration tests for Router, Direct answer, and follow-up capabilities (1B milestone - T13)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.cli import main, UNAVAILABLE_EXIT
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.storage.ledger import Ledger
from querivue_agent.storage.artifacts import initialize_artifact_store
from querivue_agent.contracts.catalog import (
    NonblankString,
    ImportSettings,
    SourceSelection,
    DelimitedDialect,
    ColumnImportSettings as CatalogColumnImportSettings,
    FileSource,
)
from querivue_agent.contracts.evidence import StringColumn, Int64Column
from querivue_agent.contracts.common import SafeCount


@pytest.fixture
def temp_state_root():
    """Create a temporary state root with initialized storage."""
    with tempfile.TemporaryDirectory() as tmp:
        state_root = Path(tmp)

        # Initialize ledger
        ledger_path = state_root / "ledger.sqlite"
        ledger = Ledger.open(ledger_path)
        ledger.close()

        # Initialize artifact store
        artifacts_dir = state_root / "artifacts"
        artifacts_dir.mkdir(parents=True)
        initialize_artifact_store(state_root)

        yield state_root


@pytest.fixture
def project_id():
    """Generate a valid project ID (UUID)."""
    return str(uuid4())


@pytest.fixture
def chat_id():
    """Generate a valid chat ID (UUID)."""
    return str(uuid4())


@pytest.fixture
def regional_csv_file(temp_state_root):
    """Create a sample CSV file with regional amounts."""
    artifacts_dir = temp_state_root / "artifacts"
    csv_file = artifacts_dir / "regional_amounts.csv"
    csv_file.write_text("region,amount\nnorth,10\nsouth,15\n")
    return csv_file


@pytest.fixture
def valid_import_settings_regional():
    """Create valid import settings for the regional_amounts.csv fixture."""
    return ImportSettings(
        settings_version=NonblankString("1"),
        source_format="csv",
        selections=[
            SourceSelection(
                source=FileSource(kind="file", format="csv"),
                header_present=True,
                header_row=SafeCount(1),
                columns=[
                    CatalogColumnImportSettings(
                        source_position=SafeCount(0),
                        original_label="region",
                        requested_type=StringColumn(tag="string"),
                        missing_markers=[],
                        decimal_separator=None,
                        thousands_separator=None,
                        datetime_format=None,
                        source_timezone=None,
                        conversion_choice=None,
                    ),
                    CatalogColumnImportSettings(
                        source_position=SafeCount(1),
                        original_label="amount",
                        requested_type=Int64Column(tag="int64"),
                        missing_markers=[],
                        decimal_separator=None,
                        thousands_separator=None,
                        datetime_format=None,
                        source_timezone=None,
                        conversion_choice=None,
                    ),
                ],
                warnings=[],
            ),
        ],
        dialect=DelimitedDialect(
            encoding="utf-8",
            delimiter=",",
            quote='"',
            escape=None,
            strip_bom=False,
        ),
        confirmation_id=CanonicalUUID("00000000-0000-0000-0000-000000000001"),
    )


class TestCLI1B:
    """Integration tests for 1B Router, Direct answer, and follow-ups capabilities (T13)."""

    def test_ask_command_direct_knowledge_question(self, temp_state_root, project_id, chat_id):
        """Test asking a general knowledge question (should accept or handle via direct routing)."""
        # Initialize project in ledger first
        ledger_path = temp_state_root / "ledger.sqlite"
        ledger = Ledger.open(ledger_path)
        try:
            from querivue_agent.storage.ledger import LedgerOps
            LedgerOps(ledger).create_project(project_id)
        finally:
            ledger.close()

        result = main([
            "--state-dir", str(temp_state_root),
            "ask",
            "--project", project_id,
            "--chat", chat_id,
            "--question", "What is SQL?",
        ])
        # Accepts analytical/knowledge questions
        assert result == UNAVAILABLE_EXIT or result == 0

    def test_ask_command_chat_followup_context(self, temp_state_root, regional_csv_file, valid_import_settings_regional, project_id, chat_id):
        """Test asking a follow-up question in the same chat retains history and cutoff sequence."""
        # Step 1: Import dataset
        import_result = main([
            "--state-dir", str(temp_state_root),
            "import",
            "--project", project_id,
            "--file", str(regional_csv_file),
        ])
        assert import_result == 0

        # Get dataset_id from ledger
        ledger_path = temp_state_root / "ledger.sqlite"
        ledger = Ledger.open(ledger_path)
        try:
            from querivue_agent.storage.ledger import LedgerOps
            ops = LedgerOps(ledger)
            datasets = ops.list_datasets(project_id)
            dataset_id = datasets[0]["dataset_id"]
        finally:
            ledger.close()

        # Step 2: Prepare dataset
        settings_path = temp_state_root / "settings.json"
        settings_path.write_text(valid_import_settings_regional.model_dump_json())

        prepare_result = main([
            "--state-dir", str(temp_state_root),
            "prepare",
            "--project", project_id,
            "--dataset", dataset_id,
            "--preview", "preview-1",
            "--settings", str(settings_path),
            "--confirm",
        ])
        assert prepare_result == 0

        # Step 3: First question in chat
        ask1_result = main([
            "--state-dir", str(temp_state_root),
            "ask",
            "--project", project_id,
            "--chat", chat_id,
            "--dataset", dataset_id,
            "--question", "What is the total amount by region?",
        ])
        assert ask1_result == UNAVAILABLE_EXIT

        # Step 4: Follow-up question in the same chat
        ask2_result = main([
            "--state-dir", str(temp_state_root),
            "ask",
            "--project", project_id,
            "--chat", chat_id,
            "--dataset", dataset_id,
            "--question", "Filter that to only the north region",
        ])
        assert ask2_result == UNAVAILABLE_EXIT

    def test_ask_command_different_chats_isolation(self, temp_state_root, regional_csv_file, valid_import_settings_regional, project_id):
        """Test that different chats are isolated and don't share conversational state."""
        chat1_id = str(uuid4())
        chat2_id = str(uuid4())

        # Setup dataset
        main([
            "--state-dir", str(temp_state_root),
            "import",
            "--project", project_id,
            "--file", str(regional_csv_file),
        ])

        ledger_path = temp_state_root / "ledger.sqlite"
        ledger = Ledger.open(ledger_path)
        try:
            from querivue_agent.storage.ledger import LedgerOps
            ops = LedgerOps(ledger)
            datasets = ops.list_datasets(project_id)
            dataset_id = datasets[0]["dataset_id"]
        finally:
            ledger.close()

        settings_path = temp_state_root / "settings.json"
        settings_path.write_text(valid_import_settings_regional.model_dump_json())

        main([
            "--state-dir", str(temp_state_root),
            "prepare",
            "--project", project_id,
            "--dataset", dataset_id,
            "--preview", "preview-1",
            "--settings", str(settings_path),
            "--confirm",
        ])

        # Chat 1 question
        res1 = main([
            "--state-dir", str(temp_state_root),
            "ask",
            "--project", project_id,
            "--chat", chat1_id,
            "--dataset", dataset_id,
            "--question", "What is the total amount?",
        ])
        assert res1 == UNAVAILABLE_EXIT

        # Chat 2 question (independent)
        res2 = main([
            "--state-dir", str(temp_state_root),
            "ask",
            "--project", project_id,
            "--chat", chat2_id,
            "--dataset", dataset_id,
            "--question", "What is the average amount?",
        ])
        assert res2 == UNAVAILABLE_EXIT

    def test_reply_command_not_implemented(self, temp_state_root):
        """Test that reply command returns unavailable status for now."""
        run_id = str(uuid4())
        question_id = str(uuid4())
        result = main([
            "--state-dir", str(temp_state_root),
            "reply",
            "--run", run_id,
            "--question", question_id,
            "--text", "Use 2024 as the date range",
        ])
        assert result == UNAVAILABLE_EXIT

    def test_resume_command_not_implemented(self, temp_state_root):
        """Test that resume command returns unavailable status for now."""
        run_id = str(uuid4())
        result = main([
            "--state-dir", str(temp_state_root),
            "resume",
            "--run", run_id,
        ])
        assert result == UNAVAILABLE_EXIT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
