"""CLI for drafting, approval, and local application history."""

import argparse
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from . import __version__
from .contracts import EvidenceLibrary, JobSnapshot
from .documents import DocumentError, render_docx
from .drafting import DraftValidationError, build_draft
from .importing import import_evidence, import_job
from .matching import match
from .model import ModelError
from .model_selection import read_saved_selection, suggest_selection
from .storage import WorkspaceError, approve_draft, approved_markdown, history, record_application

WORKSPACE_DIRECTORIES = ("imports", "resumes", "projects", "jobs", "applications")


ContractType = TypeVar("ContractType", bound=BaseModel)


def _read_contract(
    parser: argparse.ArgumentParser, path: Path, label: str, contract: type[ContractType]
) -> ContractType:
    try:
        return contract.model_validate_json(path.read_bytes())
    except OSError as exc:
        parser.exit(1, f"Could not read {label}: {exc.strerror or exc}\n")
    except ValidationError as exc:
        details = ", ".join(
            f"{'.'.join(map(str, error['loc'])) or 'document'} ({error['type']})"
            for error in exc.errors(include_input=False, include_url=False)
        )
        parser.exit(2, f"Invalid {label} JSON: {details}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career-agent", description="Local-first career assistant foundation")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show implemented features")
    init = commands.add_parser("init", help="Create an empty personal workspace")
    init.add_argument("--workspace", required=True, type=Path, help="Path to the personal workspace")
    match_command = commands.add_parser("match", help="Rank evidence against a normalized job")
    draft_command = commands.add_parser("draft", help="Create an offline resume draft and reports")
    approve_command = commands.add_parser("approve", help="Approve an exact draft after reviewing its files")
    apply_command = commands.add_parser("record-application", help="Record a submission you already made")
    history_command = commands.add_parser("history", help="List approved versions and application records")
    export_command = commands.add_parser("export-docx", help="Render an approved resume as a local DOCX")
    export_command.add_argument("--resume", required=True, help="Approved resume ID")
    export_command.add_argument("--output", required=True, type=Path, help="New .docx file to write")
    for command in (approve_command, apply_command, history_command, export_command):
        command.add_argument("--workspace", required=True, type=Path, help="Personal workspace path")
    approve_command.add_argument("--draft-dir", required=True, type=Path, help="Directory of reviewed draft files")
    apply_command.add_argument("--resume", required=True, help="Approved resume ID")
    apply_command.add_argument("--submitted-on", type=date.fromisoformat, help="Submission date (YYYY-MM-DD)")
    apply_command.add_argument("--method", help="How you submitted the application")
    apply_command.add_argument("--notes", help="Optional application notes")

    for command in (match_command, draft_command, approve_command):
        command.add_argument("--job", required=True, type=Path, help="Job snapshot JSON")
        command.add_argument("--evidence", required=True, type=Path, help="Evidence library JSON")
    draft_command.add_argument("--output-dir", required=True, type=Path, help="New directory for draft files")
    draft_command.add_argument("--use-openai", action="store_true", help="Send candidate facts to OpenAI for selection")

    job_import = commands.add_parser("import-job", help="Propose a job snapshot using OpenAI")
    job_import.add_argument("--source", required=True, type=Path, help="One raw job posting")
    job_import.add_argument("--job-id", required=True, help="Stable lowercase ID for this job")
    job_import.add_argument("--job-version", type=int, default=1, help="Job snapshot version")
    job_import.add_argument("--employer", help="Employer, if missing from the posting")
    job_import.add_argument("--title", help="Role title, if missing from the posting")
    job_import.add_argument("--evidence", type=Path, help="Existing library for compatible capability labels")
    evidence_import = commands.add_parser("import-evidence", help="Propose evidence from documents using OpenAI")
    evidence_import.add_argument("--source", required=True, action="append", type=Path, help="Source document; repeat for each")
    evidence_import.add_argument("--existing", type=Path, help="Prior library to keep alongside new or revised sources")
    for command in (job_import, evidence_import):
        command.add_argument("--use-openai", required=True, action="store_true", help="Send extracted text to OpenAI")
        command.add_argument("--output", required=True, type=Path, help="New JSON file to review and save locally")
    args = parser.parse_args(argv)

    if args.command in {"import-job", "import-evidence"}:
        return _run_import(parser, args)

    if args.command == "export-docx":
        if args.output.suffix.lower() != ".docx":
            parser.exit(2, "Output must end in .docx.\n")
        try:
            markdown = approved_markdown(args.workspace, args.resume)
            _write_new(args.output, render_docx(markdown))
        except (DocumentError, WorkspaceError, OSError, sqlite3.Error) as exc:
            parser.exit(2, f"Could not export DOCX: {exc}\n")
        print(f"DOCX exported from approved resume {args.resume}: {args.output}")
        return 0

    if args.command in {"match", "draft", "approve"}:
        job = _read_contract(parser, args.job, "job", JobSnapshot)
        library = _read_contract(parser, args.evidence, "evidence", EvidenceLibrary)
        if args.command == "match":
            print(json.dumps(asdict(match(job, library)), indent=2))
            return 0

        try:
            selected_ids = None
            if args.command == "approve":
                selected_ids = read_saved_selection(args.draft_dir)
            elif args.use_openai:
                if args.output_dir.exists():
                    parser.exit(1, "Output path already exists. Choose a new --output-dir.\n")
                selected_ids = suggest_selection(job, library)
            draft = build_draft(job, library, selected_ids)
        except (DraftValidationError, ModelError, OSError) as exc:
            parser.exit(2, f"Draft validation failed: {exc}\n")
        if args.command == "approve":
            try:
                resume_id = approve_draft(args.workspace, args.draft_dir, job, draft)
            except WorkspaceError as exc:
                parser.exit(2, f"Approval refused: {exc}\n")
            except (OSError, sqlite3.Error) as exc:
                parser.exit(1, f"Could not save approval: {exc}\n")
            print(f"Approved resume: {resume_id}")
            return 0

        try:
            args.output_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            parser.exit(1, "Output path already exists. Choose a new --output-dir.\n")
        except OSError as exc:
            parser.exit(1, f"Could not create output directory: {exc.strerror or exc}\n")

        try:
            for name, content in draft.files():
                with (args.output_dir / name).open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
        except OSError as exc:
            parser.exit(1, f"Could not finish writing draft files: {exc.strerror or exc}\n")

        print(f"Draft {draft.draft_id} is ready for review in {args.output_dir}")
        print("Review status: DRAFT")
        return 0

    if args.command in {"record-application", "history"}:
        try:
            if args.command == "history":
                print(json.dumps(history(args.workspace), indent=2))
                return 0
            record_application(
                args.workspace, args.resume, submitted_on=args.submitted_on,
                method=args.method, notes=args.notes,
            )
        except WorkspaceError as exc:
            parser.exit(2, f"Application record refused: {exc}\n")
        except (OSError, sqlite3.Error) as exc:
            parser.exit(1, f"Could not access workspace history: {exc}\n")
        print(f"User-reported submission recorded for {args.resume}")
        return 0

    if args.command == "status":
        print("Career Agent supports offline resume drafts, approvals, and local application history.")
        return 0
    if args.command == "init":
        try:
            args.workspace.mkdir(parents=True, exist_ok=True)
            for directory in WORKSPACE_DIRECTORIES:
                (args.workspace / directory).mkdir(exist_ok=True)
        except OSError as exc:
            parser.exit(1, f"Could not initialize workspace: {exc.strerror or exc}\n")
        print(f"Workspace ready: {args.workspace}")
        print("Existing files were left unchanged. Keep personal data out of Git.")
        return 0
    return 1


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _run_import(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.output.suffix.lower() != ".json" or args.output.exists():
        parser.exit(2, "Choose a new .json output path.\n")
    try:
        if args.command == "import-job":
            library = _read_contract(parser, args.evidence, "evidence", EvidenceLibrary) if args.evidence else None
            result = import_job(
                args.source, args.job_id, args.job_version, library,
                employer=args.employer, title=args.title,
            )
        else:
            library = _read_contract(parser, args.existing, "existing evidence", EvidenceLibrary) if args.existing else None
            result = import_evidence(args.source, library)
        _write_new(args.output, (result.model_dump_json(indent=2) + "\n").encode("utf-8"))
    except (ModelError, DocumentError, OSError) as exc:
        parser.exit(2, f"Import failed: {exc}\n")
    except ValidationError:
        parser.exit(2, "Import failed: the proposal does not meet the job or evidence schema.\n")
    print(f"Review the proposed JSON before drafting: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
