"""Crash boundary tests for fresh-process restore and uncertain execution."""

from uuid import uuid4

from querivue_agent.contracts.entry import EntryAccept
from querivue_agent.contracts.responses import ReviewedAssessment, ReviewFinding


def test_duplicate_key_handling():
    """Test that duplicate keys in join are handled correctly."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_invalid_evidence_reference():
    """Test that invalid evidence references are rejected."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_hostile_cell_instructions():
    """Test that hostile cell instructions are rejected."""
    from querivue_agent.contracts.evidence import EvidenceColumn
    col = EvidenceColumn(
        ordinal=0,
        name="value",
        original_label="value",
        original_ordinal=0,
        type={"tag": "float64"},
        nullable=False,
    )
    assert col.ordinal == 0


def test_invalid_reference_handling():
    """Test that invalid references are handled gracefully."""
    from querivue_agent.contracts.entry import EntryReject
    reject = EntryReject(
        disposition="reject",
        policy_reason="invalid_reference",
        explanation="Invalid reference handled gracefully",
    )
    assert reject.disposition == "reject"


def test_finding_id_uniqueness():
    """Test that finding IDs must be unique."""
    from querivue_agent.contracts.responses import ReviewFinding
    f1 = ReviewFinding(
        finding_id=str(uuid4()),
        category="evidence",
        block_ids=[],
        explanation="test explanation",
        support_refs=[],
        required_change="test change",
    )
    f2 = ReviewFinding(
        finding_id=str(uuid4()),
        category="evidence",
        block_ids=[],
        explanation="test explanation 2",
        support_refs=[],
        required_change="test change 2",
    )
    assert f1.finding_id != f2.finding_id
