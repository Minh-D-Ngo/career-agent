"""Local draft approval and application records."""

import hashlib
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from .contracts import JobSnapshot
from .drafting import DraftArtifacts


DATABASE_NAME = "career_agent.sqlite3"
SCHEMA = """
CREATE TABLE IF NOT EXISTS job_snapshots (
    job_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    PRIMARY KEY (job_id, version)
);

CREATE TABLE IF NOT EXISTS approved_resumes (
    resume_id TEXT PRIMARY KEY NOT NULL,
    job_id TEXT NOT NULL,
    job_version INTEGER NOT NULL,
    markdown BLOB NOT NULL,
    evidence_json BLOB NOT NULL,
    gaps_json BLOB NOT NULL,
    content_sha256 TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    FOREIGN KEY (job_id, job_version) REFERENCES job_snapshots (job_id, version)
);

CREATE TABLE IF NOT EXISTS applications (
    resume_id TEXT PRIMARY KEY NOT NULL REFERENCES approved_resumes (resume_id),
    recorded_at TEXT NOT NULL,
    submitted_on TEXT,
    method TEXT,
    notes TEXT
);
"""


class WorkspaceError(ValueError):
    """An operation conflicts with the reviewed files or saved history."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(database: Path, *, create: bool = False, readonly: bool = False) -> sqlite3.Connection:
    mode = "ro" if readonly else "rwc" if create else "rw"
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def approve_draft(
    workspace: Path, draft_dir: Path, job: JobSnapshot, expected: DraftArtifacts,
) -> str:
    if not expected.claim_count:
        raise WorkspaceError("There are no supported claims to approve.")

    reviewed: dict[str, bytes] = {}
    for name, content in expected.files():
        reviewed[name] = (draft_dir / name).read_bytes()
        if reviewed[name] != content.encode("utf-8"):
            raise WorkspaceError(
                f"{name} differs from the validated draft. "
                "Generate a fresh draft from these inputs and review it before approving."
            )

    payload = (
        job.id, job.version, reviewed["draft.md"], reviewed["evidence.json"], reviewed["gaps.json"],
    )
    snapshot_json = job.model_dump_json()
    workspace.mkdir(parents=True, exist_ok=True)
    with closing(_connect(workspace / DATABASE_NAME, create=True)) as connection:
        connection.executescript(SCHEMA)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO job_snapshots VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (job.id, job.version, snapshot_json),
            )
            stored_job = connection.execute(
                "SELECT snapshot_json FROM job_snapshots WHERE job_id = ? AND version = ?",
                (job.id, job.version),
            ).fetchone()
            if stored_job["snapshot_json"] != snapshot_json:
                raise WorkspaceError("This job version already has a different snapshot. Increment its version.")

            stored_resume = connection.execute(
                """SELECT job_id, job_version, markdown, evidence_json, gaps_json
                   FROM approved_resumes WHERE resume_id = ?""",
                (expected.draft_id,),
            ).fetchone()
            if stored_resume is not None:
                if tuple(stored_resume) != payload:
                    raise WorkspaceError("This resume ID already belongs to a different approved version.")
                return expected.draft_id

            connection.execute(
                """INSERT INTO approved_resumes
                   (resume_id, job_id, job_version, markdown, evidence_json, gaps_json,
                    content_sha256, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (expected.draft_id, *payload, hashlib.sha256(reviewed["draft.md"]).hexdigest(), _now()),
            )
    return expected.draft_id


def record_application(
    workspace: Path, resume_id: str, *, submitted_on: date | None = None,
    method: str | None = None, notes: str | None = None,
) -> None:
    database = workspace / DATABASE_NAME
    missing = "No approved resume has that ID. Review and approve the exact draft first."
    if not database.is_file():
        raise WorkspaceError(missing)

    details = (submitted_on.isoformat() if submitted_on else None, method, notes)
    with closing(_connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM approved_resumes WHERE resume_id = ?", (resume_id,),
        ).fetchone() is None:
            raise WorkspaceError(missing)

        recorded = connection.execute(
            "SELECT submitted_on, method, notes FROM applications WHERE resume_id = ?",
            (resume_id,),
        ).fetchone()
        if recorded is not None:
            if tuple(recorded) != details:
                raise WorkspaceError("An application with different details is already recorded for this resume.")
            return

        connection.execute(
            """INSERT INTO applications (resume_id, recorded_at, submitted_on, method, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (resume_id, _now(), *details),
        )


def history(workspace: Path) -> list[dict]:
    database = workspace / DATABASE_NAME
    if not database.is_file():
        return []
    with closing(_connect(database, readonly=True)) as connection:
        rows = connection.execute(
            """SELECT r.resume_id, r.job_id, r.job_version, r.content_sha256, r.approved_at,
                      'APPROVED' AS review_status,
                      CASE WHEN a.resume_id IS NULL THEN 'NOT_RECORDED'
                           ELSE 'USER_REPORTED_SUBMITTED' END AS application_status,
                      a.recorded_at, a.submitted_on, a.method, a.notes
               FROM approved_resumes AS r LEFT JOIN applications AS a USING (resume_id)
               ORDER BY r.approved_at, r.resume_id"""
        )
        return [dict(row) for row in rows]
