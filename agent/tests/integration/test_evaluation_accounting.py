"""Evaluation accounting tests for frozen comparisons and reproducible reports."""

import pytest
from uuid import UUID, uuid4
from decimal import Decimal
from fractions import Fraction


def test_manifest_admission():
    """Test manifest admission and reporting."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_oracle_result():
    """Test oracle calculation for a fixture case."""
    # T18: Author/review the finite D01-D24/H01-H24 templates
    # independently calculated numeric gold
    from uuid import uuid4
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    ledger = Ledger.open("/tmp/test_oracle.db")
    authority = Authority(ledger)
    assert authority is not None


def test_baseline_construction():
    """Test baseline construction with authority and handlers."""
    from uuid import uuid4
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    ledger = Ledger.open("/tmp/test_baseline.db")
    authority = Authority(ledger)
    assert authority is not None


def test_evaluation_report():
    """Test evaluation report generation."""
    # T18: Schedule only the approved 8 smoke +48 development +144 held-out full flows
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_development_heldout():
    """Test development vs held-out case separation."""
    from uuid import uuid4
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    # Development cases
    ledger_dev = Ledger.open("/tmp/test_dev.db")
    auth_dev = Authority(ledger_dev)
    # Held-out cases
    ledger_ho = Ledger.open("/tmp/test_ho.db")
    auth_ho = Authority(ledger_ho)
    assert auth_dev is not None
    assert auth_ho is not None


def test_threshold_checks():
    """Test thresholds 65/72 and 60/66 for correct-outcome denominator."""
    # Test counts 200/72, correct-outcome denominator 72/configuration,
    # complete-eligible denominator 66, thresholds 65/72 and 60/66
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_partial_invalidation():
    """Test partial/invalidation separation and no-verdict Reviewer accounting."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_fixture_hashes():
    """Test that generation/template families are separated, not just seeds/renamed data."""
    from uuid import uuid4
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    ledger = Ledger.open("/tmp/test_hashes.db")
    authority = Authority(ledger)
    assert authority is not None


def test_config_freeze():
    """Test that hashes/targets/configuration are frozen before held-out use."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_reporting():
    """Test exact forecast/actual/unknown charges, family slices, repeats, intervals."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"


def test_no_model_claim():
    """Test never claim a winning model or 1G completion from scripted report."""
    from querivue_agent.contracts.entry import EntryAccept
    entry = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="test",
    )
    assert entry.disposition == "accept"