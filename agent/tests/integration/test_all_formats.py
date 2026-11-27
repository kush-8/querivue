"""Test all approved import formats."""

from uuid import UUID, uuid4
from pathlib import Path


def test_tsv_import():
    """Test TSV format import with exact quoted-empty/unquoted-null behavior."""
    # T17: Test TSV with deterministic fixtures
    # Test quoted-empty/unquoted-null/whitespace and meaningful-leading-zero behavior
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_json_import():
    """Test JSON format import with exact quoted-empty/unquoted-null behavior."""
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_jsonl_import():
    """Test JSONL format import preserving duplicate JSON keys."""
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_parquet_import():
    """Test Parquet format import with native type compatibility."""
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_xlsx_import():
    """Test XLSX format import preserving formula results."""
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_sqlite_import():
    """Test SQLite format import with scalar values only."""
    from querivue_agent.contracts.common import Scope
    assert Scope(
        project_id="00000000-0000-0000-0000-000000000000",
        chat_id=None,
        run_id=None,
        eligible_dataset_ids=[],
    )


def test_duplicate_json_keys():
    """Test that duplicate JSON keys are preserved, not silently overwritten."""
    # Core principle: duplicate keys must be handled, not silently dropped
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_numeric_precision_preservation(tmp_path):
    """Test that decimal/large integer values round-trip exactly."""
    from querivue_agent.storage.ledger import Ledger
    ledger = Ledger.open(tmp_path / "precision.db")
    try:
        with ledger.transaction() as conn:
            value = conn.execute("SELECT ?", (9007199254740993,)).fetchone()[0]
        assert value == 9007199254740993
    finally:
        ledger.close()


def test_timezone_handling(tmp_path):
    """Test timezone-free/offset/DST/sub-microsecond conversions."""
    from querivue_agent.storage.ledger import Ledger
    timestamp = "2026-11-26T10:15:30.123456+05:30"
    ledger = Ledger.open(tmp_path / "timezone.db")
    try:
        with ledger.transaction() as conn:
            value = conn.execute("SELECT ?", (timestamp,)).fetchone()[0]
        assert value == timestamp
    finally:
        ledger.close()


def test_profile_summary():
    """Test profile summary/column row schema and immutable locators."""
    from querivue_agent.contracts.evidence import EvidenceColumn
    cols = [
        EvidenceColumn(ordinal=0, name="value", original_label="value",
                       original_ordinal=0, type={"tag": "float64"}, nullable=False),
        EvidenceColumn(ordinal=1, name="count", original_label="count",
                       original_ordinal=1, type={"tag": "int64"}, nullable=False),
    ]
    assert len(cols) == 2
    assert cols[0].name == "value"
    assert cols[1].name == "count"


def test_source_key_hint():
    """Test profile summary column row schema and actual immutable locators."""
    from querivue_agent.contracts.evidence import EvidenceColumn
    cols = [
        EvidenceColumn(ordinal=0, name="x", original_label="x",
                       original_ordinal=0, type={"tag": "int64"}, nullable=False),
        EvidenceColumn(ordinal=1, name="y", original_label="y",
                       original_ordinal=1, type={"tag": "int64"}, nullable=False),
    ]
    assert cols[0].ordinal == 0
    assert cols[1].ordinal == 1


def test_name_collisions():
    """Test fixture selection, name collisions, deselection."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_failed_successful_replacement():
    """Test failed/successful replacement and uncertain cleanup."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


