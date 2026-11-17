"""Minimal CLI: report status and initialize an explicitly chosen workspace."""

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__

WORKSPACE_DIRECTORIES = ("imports", "resumes", "projects", "jobs", "applications")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career-agent", description="Local-first career assistant foundation")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show implemented features")
    init = commands.add_parser("init", help="Create an empty personal workspace")
    init.add_argument("--workspace", required=True, type=Path, help="Path to the personal workspace")
    args = parser.parse_args(argv)

    if args.command == "status":
        print("Career Agent foundation is ready. No resume workflow is implemented yet.")
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
