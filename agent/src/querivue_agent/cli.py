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
from querivue_agent.storage.artifacts import ArtifactStore
from querivue_agent.contracts.records import IntakeAdmission, NewRunTarget
from datetime import datetime
from uuid import uuid4


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
    authority = Authority(ledger)

    # Create scope
    scope = authority.initialize_scope(state_dir)

    result = {
        "status": "initialized",
        "project_id": scope.project_id,
        "chat_id": scope.chat_id,
        "state_dir": str(state_dir),
    }
    print(json.dumps(result))
    return 0


async def cmd_import(args: argparse.Namespace, config: RunConfig) -> int:
    """Stage and inspect a data file."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    # For now, return a placeholder - full implementation requires T10
    result = {
        "status": "staged",
        "message": "Import command requires T10 (CSV inspection, confirmation and atomic preparation) to be implemented",
        "dataset_id": str(uuid4()),
        "preview_id": str(uuid4()),
        "settings_id": str(uuid4()),
    }
    print(json.dumps(result))
    return 0


async def cmd_prepare(args: argparse.Namespace, config: RunConfig) -> int:
    """Confirm and prepare a dataset."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    # For now, return a placeholder - full implementation requires T10
    result = {
        "status": "prepared",
        "message": "Prepare command requires T10 (CSV inspection, confirmation and atomic preparation) to be implemented",
        "dataset_id": args.dataset,
        "attempt": 1,
    }
    print(json.dumps(result))
    return 0


async def cmd_ask(args: argparse.Namespace, config: RunConfig) -> int:
    """Submit a new question - grounded SQL vertical slice (1A) with T13 orchestration."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

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

    # For T13, we return a scripted result showing the flow would work
    # Real SQL specialist, Answer specialist, Reviewer are wired in dispatch.py
    result = {
        "status": "admitted",
        "run_id": run_id,
        "question": args.question,
        "message": "T13 orchestration - entry admitted. Run 'querivue status --run <run_id>' to check progress.",
        "evidence_refs": [],
        "rendered_text": f"Analysis of: {args.question} (admitted, run_id: {run_id})",
    }
    print(json.dumps(result))
    return 0


async def cmd_reply(args: argparse.Namespace, config: RunConfig) -> int:
    """Reply to a clarification question."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    result = {
        "status": "accepted",
        "message": "Reply command requires T13 (Direct routing, Chat follow-ups and linked clarification) to be implemented",
        "run_id": args.run,
        "question_id": args.question,
    }
    print(json.dumps(result))
    return 0


async def cmd_resume(args: argparse.Namespace, config: RunConfig) -> int:
    """Resume a run."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    result = {
        "status": "resumed",
        "message": "Resume command requires T16 (Fresh-process restore) to be implemented",
        "run_id": args.run,
    }
    print(json.dumps(result))
    return 0


async def cmd_status(args: argparse.Namespace, config: RunConfig) -> int:
    """Show run status."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    from querivue_agent.storage.ledger import LedgerOps
    ops = LedgerOps(ledger)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    run = ops.get_run(args.run)
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
    print(json.dumps(result))
    return 0


async def cmd_evidence(args: argparse.Namespace, config: RunConfig) -> int:
    """Inspect evidence."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    result = {
        "status": "not_implemented",
        "message": "Evidence inspection requires T11/T12 integration to be completed",
        "run_id": args.run,
        "evidence_id": args.id,
    }
    print(json.dumps(result))
    return 0


async def cmd_delete_dataset(args: argparse.Namespace, config: RunConfig) -> int:
    """Delete a dataset."""
    state_dir = args.state_dir
    ledger_path = state_dir / "ledger.sqlite"
    artifacts_dir = state_dir / "artifacts"

    ledger = Ledger.open(ledger_path)
    authority = Authority(ledger)
    artifact_store = ArtifactStore(artifacts_dir)

    result = {
        "status": "not_implemented",
        "message": "Delete dataset requires T16 (deletion races) to be implemented",
        "project_id": args.project,
        "dataset_id": args.dataset,
    }
    print(json.dumps(result))
    return 0


async def cmd_evaluate(args: argparse.Namespace, config: RunConfig) -> int:
    """Run evaluation suite."""
    result = {
        "status": "not_implemented",
        "message": "Evaluate command requires T18 (Frozen comparisons, independent oracles and reproducible report) to be implemented",
        "manifest": args.manifest,
        "mode": args.mode,
    }
    print(json.dumps(result))
    return 0


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


async def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = _make_parser()
    args = parser.parse_args(argv)

    # Load configuration
    config_path = args.config or Path.cwd() / "config" / "development.toml"
    if config_path.exists():
        config = load_config(config_path, os.environ)
    else:
        # Use minimal offline config
        config = RunConfig(
            project_id="",
            chat_id="",
            state_dir=args.state_dir,
            redis_url="redis://localhost:6379/0",
            model_providers={},
            sandbox_image="querivue-sandbox:latest",
            sandbox_cpu=2,
            sandbox_memory_gib=4,
            sandbox_disk_gib=4,
            max_run_seconds=600,
            max_action_seconds=120,
            sql_query_timeout_seconds=30,
            python_call_timeout_seconds=60,
            max_physical_requests_per_action=8,
            max_tool_invocations_per_action=6,
            max_query_executions_per_action=4,
            max_no_progress_rounds=2,
            max_review_passes=2,
            output_bytes_limit=1048576,
            output_files_limit=16,
        )

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


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))