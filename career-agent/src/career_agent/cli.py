"""CLI for local workspace setup, matching, and drafting."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from . import __version__
from .contracts import EvidenceLibrary, JobSnapshot
from .drafting import DraftValidationError, build_draft
from .matching import match

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
    for command in (match_command, draft_command):
        command.add_argument("--job", required=True, type=Path, help="Job snapshot JSON")
        command.add_argument("--evidence", required=True, type=Path, help="Evidence library JSON")
    draft_command.add_argument("--output-dir", required=True, type=Path, help="New directory for draft files")
    args = parser.parse_args(argv)

    if args.command in {"match", "draft"}:
        job = _read_contract(parser, args.job, "job", JobSnapshot)
        library = _read_contract(parser, args.evidence, "evidence", EvidenceLibrary)
        if args.command == "match":
            print(json.dumps(asdict(match(job, library)), indent=2))
            return 0

        try:
            draft = build_draft(job, library)
        except DraftValidationError as exc:
            parser.exit(2, f"Draft validation failed: {exc}\n")
        try:
            args.output_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            parser.exit(1, "Output path already exists. Choose a new --output-dir.\n")
        except OSError as exc:
            parser.exit(1, f"Could not create output directory: {exc.strerror or exc}\n")

        try:
            for name, content in (
                ("draft.md", draft.markdown), ("evidence.json", draft.evidence_json),
                ("gaps.json", draft.gaps_json),
            ):
                with (args.output_dir / name).open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
        except OSError as exc:
            parser.exit(1, f"Could not finish writing draft files: {exc.strerror or exc}\n")

        print(f"Draft {draft.draft_id} is ready for review in {args.output_dir}")
        print("Review status: DRAFT")
        return 0

    if args.command == "status":
        print("Career Agent can match evidence and create offline resume drafts for review.")
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


if __name__ == "__main__":
    raise SystemExit(main())
