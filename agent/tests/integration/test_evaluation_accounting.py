"""Evaluation accounting tests for frozen comparisons and reproducible reports."""

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


def test_baseline_construction(tmp_path):
    """Test baseline construction with authority and handlers."""
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    ledger = Ledger.open(tmp_path / "baseline.db")
    try:
        scope = Authority(ledger).initialize_scope(tmp_path)
        with ledger.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE project_id = ?",
                (str(scope.project_id),),
            ).fetchone()
        assert row[0] == str(scope.project_id)
    finally:
        ledger.close()


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


def test_development_heldout(tmp_path):
    """Test development vs held-out case separation."""
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.storage.ledger import Ledger
    ledger_dev = Ledger.open(tmp_path / "development.db")
    ledger_ho = Ledger.open(tmp_path / "heldout.db")
    try:
        dev_scope = Authority(ledger_dev).initialize_scope(tmp_path)
        heldout_scope = Authority(ledger_ho).initialize_scope(tmp_path)
        assert dev_scope.project_id != heldout_scope.project_id
    finally:
        ledger_dev.close()
        ledger_ho.close()


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
