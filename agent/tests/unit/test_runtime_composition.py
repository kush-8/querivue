"""Runtime composition checks for entry points and unavailable capabilities."""

import asyncio
import inspect
import json

import pytest


def test_console_main_is_synchronous():
    from querivue_agent.cli import main

    assert not inspect.iscoroutinefunction(main)


def test_unavailable_import_fails_before_state_changes(tmp_path, capsys):
    from querivue_agent.cli import UNAVAILABLE_EXIT, main

    state_dir = tmp_path / "state"
    exit_code = main([
        "--state-dir", str(state_dir),
        "import",
        "--project", "project-1",
        "--file", str(tmp_path / "missing.csv"),
    ])

    assert exit_code == UNAVAILABLE_EXIT
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
    assert not (state_dir / "ledger.sqlite").exists()


def test_runtime_modules_import_with_canonical_types():
    import querivue_agent.dispatch
    import querivue_agent.supervisor
    from querivue_agent.contracts.records import OperationRequest, SandboxTicket
    from querivue_agent.execution import python_runner

    assert python_runner.OperationRequest is OperationRequest
    assert python_runner.SandboxTicket is SandboxTicket


def test_python_runner_fails_closed_before_execution():
    from querivue_agent.execution.python_runner import PythonRunner

    runner = PythonRunner(config=None, sandbox=None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="ticket admission"):
        asyncio.run(runner.start())
