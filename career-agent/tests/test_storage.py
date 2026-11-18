import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from career_agent.contracts import EvidenceLibrary, JobSnapshot
from career_agent.drafting import build_draft
from career_agent.storage import DATABASE_NAME, WorkspaceError, approve_draft, history

EXAMPLES = Path(__file__).resolve().parents[1] / "data" / "examples"
JOB = EXAMPLES / "harbor-demo-job.json"
EVIDENCE = EXAMPLES / "harbor-demo-evidence.json"


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / "my workspace #1"
        self.draft_dir = self.workspace / "resumes" / "harbor"
        self.database = self.workspace / DATABASE_NAME
        self.job = JobSnapshot.model_validate_json(JOB.read_bytes())
        self.library = EvidenceLibrary.model_validate_json(EVIDENCE.read_bytes())
        self.draft = build_draft(self.job, self.library)

    def run_cli(self, *args):
        env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
        return subprocess.run(
            [sys.executable, "-m", "career_agent.cli", *map(str, args)],
            env=env, capture_output=True, text=True, check=False,
        )

    def save_draft_files(self, draft):
        self.draft_dir.mkdir(parents=True, exist_ok=True)
        for name, text in draft.files():
            (self.draft_dir / name).write_bytes(text.encode("utf-8"))

    def test_cli_approval_and_submission_are_distinct_and_idempotent(self):
        inputs = ("--job", JOB, "--evidence", EVIDENCE)
        workspace = ("--workspace", self.workspace)
        draft_result = self.run_cli("draft", *inputs, "--output-dir", self.draft_dir)
        self.assertEqual(draft_result.returncode, 0, draft_result.stderr)
        submit = (
            "record-application", *workspace, "--resume", self.draft.draft_id,
            "--submitted-on", "2026-01-16", "--method", "company site",
        )
        self.assertEqual(self.run_cli(*submit).returncode, 2)
        self.assertEqual(json.loads(self.run_cli("history", *workspace).stdout), [])
        self.assertFalse(self.database.exists())

        approval = ("approve", *workspace, *inputs, "--draft-dir", self.draft_dir)
        result = self.run_cli(*approval)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.draft.draft_id, result.stdout)
        approved, = history(self.workspace)
        self.assertEqual(approved["review_status"], "APPROVED")
        self.assertEqual(approved["application_status"], "NOT_RECORDED")
        self.assertEqual(self.run_cli(*approval).returncode, 0)
        self.assertEqual(history(self.workspace), [approved])

        result = self.run_cli(*submit)
        self.assertEqual(result.returncode, 0, result.stderr)
        applied, = json.loads(self.run_cli("history", *workspace).stdout)
        self.assertEqual(applied["resume_id"], self.draft.draft_id)
        self.assertEqual(applied["job_id"], self.job.id)
        self.assertEqual(applied["job_version"], self.job.version)
        self.assertEqual(applied["application_status"], "USER_REPORTED_SUBMITTED")
        self.assertEqual(applied["submitted_on"], "2026-01-16")
        self.assertEqual(self.run_cli(*submit).returncode, 0)
        self.assertEqual(history(self.workspace), [applied])
        self.assertEqual(self.run_cli(*submit, "--notes", "Different details").returncode, 2)
        self.assertEqual(history(self.workspace), [applied])

    def test_rejects_any_changed_review_file_before_writing(self):
        for name, _ in self.draft.files():
            with self.subTest(name=name):
                self.save_draft_files(self.draft)
                (self.draft_dir / name).write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(WorkspaceError, name):
                    approve_draft(self.workspace, self.draft_dir, self.job, self.draft)
                self.assertFalse(self.database.exists())

    def test_empty_draft_cannot_be_approved(self):
        empty = EvidenceLibrary(schema_version="1.0", records=())
        draft = build_draft(self.job, empty)
        self.save_draft_files(draft)
        with self.assertRaisesRegex(WorkspaceError, "no supported claims"):
            approve_draft(self.workspace, self.draft_dir, self.job, draft)
        self.assertFalse(self.database.exists())

    def test_new_version_preserves_exact_old_artifacts_and_job_snapshot(self):
        self.save_draft_files(self.draft)
        approve_draft(self.workspace, self.draft_dir, self.job, self.draft)
        revised_job = self.job.model_copy(update={"title": "Revised title"})
        revised_draft = build_draft(revised_job, self.library)
        self.save_draft_files(revised_draft)
        with self.assertRaisesRegex(WorkspaceError, "Increment its version"):
            approve_draft(self.workspace, self.draft_dir, revised_job, revised_draft)

        revised_job = revised_job.model_copy(update={"version": self.job.version + 1})
        revised_draft = build_draft(revised_job, self.library)
        self.save_draft_files(revised_draft)
        approve_draft(self.workspace, self.draft_dir, revised_job, revised_draft)
        self.assertNotEqual(revised_draft.draft_id, self.draft.draft_id)

        with closing(sqlite3.connect(self.database)) as connection:
            stored = connection.execute(
                """SELECT markdown, evidence_json, gaps_json, content_sha256
                   FROM approved_resumes WHERE resume_id = ?""",
                (self.draft.draft_id,),
            ).fetchone()
            snapshot, = connection.execute(
                "SELECT snapshot_json FROM job_snapshots WHERE job_id = ? AND version = ?",
                (self.job.id, self.job.version),
            ).fetchone()
        self.assertEqual(stored[:3], tuple(text.encode("utf-8") for _, text in self.draft.files()))
        self.assertEqual(stored[3], hashlib.sha256(stored[0]).hexdigest())
        self.assertEqual(JobSnapshot.model_validate_json(snapshot), self.job)
        self.assertEqual(len(history(self.workspace)), 2)
