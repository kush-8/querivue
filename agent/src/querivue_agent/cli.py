"""CLI entry point for Querivue agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Sequence
from uuid import UUID, uuid4

from querivue_agent.config import load_config, RunConfig
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.entry import EntryInput as IntakeEntryInput, EntryAccept, EntryReject, EntryClarify, EntryAssessment
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
from querivue_agent.runtime.authority import Authority
from querivue_agent.storage.ledger import Ledger
from querivue_agent.contracts.records import IntakeAdmission, NewRunTarget
from datetime import datetime


UNAVAILABLE_EXIT = 3


def _validate_config_path(path: str) -> Path:
    """Validate config file exists and is readable."""
    p = Path(path)
    if not p.exists():
        raise argparse.ArgumentTypeError(f"Config file not found: {path}")
    if not p.is_file():
        raise argparse.ArgumentTypeError(f"Not a file: {path}")
    return p


def _validate_state_dir(path: str) -> Path:
    """Validate state directory."""
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_parser() -> argparse.ArgumentParser:
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="querivue",
        description="Querivue - Analytical agent for grounded data analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help",
        action="help",
        help="Show this help message and exit",
    )
    parser.add_argument(
        "--state-dir",
        type=_validate_state_dir,
        default=Path.cwd() / ".querivue",
        help="State directory (default: .querivue in current directory)",
    )
    parser.add_argument(
        "--config",
        type=_validate_config_path,
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="querivue-agent 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new project and chat")
    init_parser.add_argument("--project", type=str, help="Project ID (optional, creates new if omitted)")

    # import command
    import_parser = subparsers.add_parser("import", help="Stage and inspect a data file")
    import_parser.add_argument("--project", required=True, type=str, help="Project ID")
    import_parser.add_argument("--file", required=True, type=str, help="Path to data file")
    import_parser.add_argument("--replace", type=str, help="Dataset ID to replace")

    # prepare command
    prepare_parser = subparsers.add_parser("prepare", help="Confirm and prepare a dataset")
    prepare_parser.add_argument("--project", required=True, type=str, help="Project ID")
    prepare_parser.add_argument("--dataset", required=True, type=str, help="Dataset ID")
    prepare_parser.add_argument("--preview", required=True, type=str, help="Preview ID to confirm")
    prepare_parser.add_argument("--settings", required=True, type=str, help="Path to import settings JSON")
    prepare_parser.add_argument("--confirm", action="store_true", help="Confirm preparation")

    # ask command
    ask_parser = subparsers.add_parser("ask", help="Submit a new question")
    ask_parser.add_argument("--project", required=True, type=str, help="Project ID")
    ask_parser.add_argument("--chat", required=True, type=str, help="Chat ID")
    ask_parser.add_argument("--dataset", action="append", type=str, help="Dataset IDs to include (repeatable)")
    ask_parser.add_argument("--question", required=True, type=str, help="Question text")

    # reply command
    reply_parser = subparsers.add_parser("reply", help="Reply to a clarification question")
    reply_parser.add_argument("--run", required=True, type=str, help="Run ID")
    reply_parser.add_argument("--question", required=True, type=str, help="Question ID")
    reply_parser.add_argument("--text", required=True, type=str, help="Reply text")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume a run")
    resume_parser.add_argument("--run", required=True, type=str, help="Run ID")

    # status command
    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("--run", required=True, type=str, help="Run ID")

    # evidence command
    evidence_parser = subparsers.add_parser("evidence", help="Inspect evidence")
    evidence_parser.add_argument("--run", required=True, type=str, help="Run ID")
    evidence_parser.add_argument("--id", required=True, type=str, help="Evidence ID")

    # delete-dataset command
    delete_parser = subparsers.add_parser("delete-dataset", help="Delete a dataset")
    delete_parser.add_argument("--project", required=True, type=str, help="Project ID")
    delete_parser.add_argument("--dataset", required=True, type=str, help="Dataset ID")

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation suite")
    eval_parser.add_argument("--manifest", required=True, type=str, help="Path to evaluation manifest")
    eval_parser.add_argument("--mode", choices=["scripted", "live"], default="scripted", help="Evaluation mode")

    return parser


async def cmd_init(args: argparse.Namespace, config: RunConfig) -> int:
    """Initialize a new project and chat."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    ledger = Ledger.open(ledger_path)
    try:
        scope = Authority(ledger).initialize_scope(state_dir)
        result = {
            "status": "initialized",
            "project_id": scope.project_id,
            "chat_id": scope.chat_id,
            "state_dir": str(state_dir),
        }
    finally:
        ledger.close()
    print(json.dumps(result))
    return 0


async def cmd_import(args: argparse.Namespace, config: RunConfig) -> int:
    """Stage and inspect a data file."""
    result = {
        "status": "unavailable",
        "message": "Import inspection and staging are not implemented",
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_prepare(args: argparse.Namespace, config: RunConfig) -> int:
    """Confirm and prepare a dataset."""
    result = {
        "status": "unavailable",
        "message": "Dataset preparation is not implemented",
        "dataset_id": args.dataset,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_ask(args: argparse.Namespace, config: RunConfig) -> int:
    """Submit a new question - grounded SQL vertical slice (1A) with T13 orchestration."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    ledger = Ledger.open(ledger_path)
    try:
        return await _cmd_ask_with_ledger(args, config, ledger)
    finally:
        ledger.close()


async def _cmd_ask_with_ledger(
    args: argparse.Namespace,
    config: RunConfig,
    ledger: Ledger,
) -> int:
    """Process an ask request using an owned ledger connection."""
    authority = Authority(ledger)
    # Parse dataset IDs
    dataset_ids = []
    if args.dataset:
        for ds in args.dataset:
            dataset_ids.append(UUID(ds))

    # Create entry input (for intake)
    intake_entry = IntakeEntryInput(
        project_id=args.project,
        chat_id=args.chat,
        question=args.question,
        eligible_dataset_ids=[str(d) for d in dataset_ids],
    )

    # Record intake
    scope = Scope(
        project_id=args.project,
        chat_id=args.chat,
        run_id=None,
        eligible_dataset_ids=[str(d) for d in dataset_ids],
    )
    intake_receipt = authority.record_intake(intake_entry, scope)

    # Run entry assessment
    from querivue_agent.entry import assess_entry
    assessment = await assess_entry(intake_entry, model=None)

    if assessment.disposition != "accept":
        result = {
            "status": "rejected",
            "disposition": assessment.disposition,
            "policy_reason": assessment.policy_reason,
            "explanation": assessment.explanation,
        }
        if assessment.disposition == "clarify":
            result["question"] = assessment.question
        print(json.dumps(result))
        return 0

    # Admit the run
    import hashlib
    context_hash = hashlib.sha256(b"context").hexdigest()
    config_hash = hashlib.sha256(b"config-v1").hexdigest()

    admission = IntakeAdmission(
        admission_id=str(uuid4()),
        intake_id=CanonicalUUID(intake_receipt.intake_id),
        submission_hash=CanonicalUUID(intake_receipt.original_hash),
        scope=scope,
        assessment=assessment,
        context_hash=CanonicalUUID(context_hash),
        configuration_hash=CanonicalUUID(config_hash),
        policy_version="1.0",
        target=NewRunTarget(kind="new_run", run_id=RuntimeUUID(str(uuid4()))),
        fence=intake_receipt.fence,
        accepted_at=datetime.utcnow().isoformat() + "Z",
    )

    admission_receipt = authority.admit(admission)
    run_id = str(admission_receipt.run_id)

    result = {
        "status": "unavailable",
        "run_id": run_id,
        "question": args.question,
        "message": "Run admitted, but graph execution is not implemented",
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_reply(args: argparse.Namespace, config: RunConfig) -> int:
    """Reply to a clarification question."""
    result = {
        "status": "unavailable",
        "message": "Clarification replies are not implemented",
        "run_id": args.run,
        "question_id": args.question,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_resume(args: argparse.Namespace, config: RunConfig) -> int:
    """Resume a run."""
    result = {
        "status": "unavailable",
        "message": "Run restoration is not implemented",
        "run_id": args.run,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_status(args: argparse.Namespace, config: RunConfig) -> int:
    """Show run status."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    ledger = Ledger.open(ledger_path)
    try:
        from querivue_agent.storage.ledger import LedgerOps
        run = LedgerOps(ledger).get_run(args.run)
        if run is None:
            result = {"status": "not_found", "run_id": args.run}
        else:
            result = {
                "status": "found",
                "run_id": args.run,
                "project_id": run.get("project_id"),
                "chat_id": run.get("chat_id"),
                "question": run.get("question"),
            }
    finally:
        ledger.close()
    print(json.dumps(result))
    return 0


async def cmd_evidence(args: argparse.Namespace, config: RunConfig) -> int:
    """Inspect evidence."""
    result = {
        "status": "not_implemented",
        "message": "Evidence inspection is not implemented",
        "run_id": args.run,
        "evidence_id": args.id,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_delete_dataset(args: argparse.Namespace, config: RunConfig) -> int:
    """Delete a dataset."""
    result = {
        "status": "not_implemented",
        "message": "Dataset deletion is not implemented",
        "project_id": args.project,
        "dataset_id": args.dataset,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


async def cmd_evaluate(args: argparse.Namespace, config: RunConfig) -> int:
    """Run evaluation suite."""
    result = {
        "status": "not_implemented",
        "message": "Evaluate command requires T18 (Frozen comparisons, independent oracles and reproducible report) to be implemented",
        "manifest": args.manifest,
        "mode": args.mode,
    }
    print(json.dumps(result))
    return UNAVAILABLE_EXIT


COMMANDS = {
    "init": cmd_init,
    "import": cmd_import,
    "prepare": cmd_prepare,
    "ask": cmd_ask,
    "reply": cmd_reply,
    "resume": cmd_resume,
    "status": cmd_status,
    "evidence": cmd_evidence,
    "delete-dataset": cmd_delete_dataset,
    "evaluate": cmd_evaluate,
}


async def _main(argv: Sequence[str] | None = None) -> int:
    """Run the asynchronous CLI implementation."""
    parser = _make_parser()
    args = parser.parse_args(argv)

    # Load configuration
    config_path = args.config or (
        Path(__file__).resolve().parents[2] / "config" / "development.toml"
    )
    config = load_config(config_path, os.environ)

    # Execute command
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"Unknown command: {args.command}")
        return 2

    try:
        return await handler(args, config)
    except Exception as e:
        result = {
            "status": "error",
            "error": str(e),
            "command": args.command,
        }
        print(json.dumps(result), file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI from synchronous module and console entry points."""
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    sys.exit(main())
