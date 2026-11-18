import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from career_agent.contracts import DraftClaim, EvidenceLibrary, JobSnapshot
from career_agent.drafting import DraftValidationError, build_draft, validate_verbatim_claim

EXAMPLES = Path(__file__).resolve().parents[1] / "data" / "examples"
JOB_PATH = EXAMPLES / "harbor-demo-job.json"
EVIDENCE_PATH = EXAMPLES / "harbor-demo-evidence.json"


class DraftingTests(unittest.TestCase):
    def setUp(self):
        self.job = JobSnapshot.model_validate_json(JOB_PATH.read_bytes())
        self.library = EvidenceLibrary.model_validate_json(EVIDENCE_PATH.read_bytes())
        self.facts = {fact.id: fact for record in self.library.records for fact in record.facts}

    def test_graph_produces_deterministic_cited_drafts_and_gaps(self):
        draft = build_draft(self.job, self.library)
        self.assertEqual(draft, build_draft(self.job, self.library))
        evidence = json.loads(draft.evidence_json)
        gaps = json.loads(draft.gaps_json)
        self.assertEqual(draft.draft_id, evidence["draft_id"])
        self.assertEqual(draft.draft_id, gaps["draft_id"])
        self.assertEqual(evidence["review_status"], "DRAFT")
        self.assertEqual(evidence["selected_record_ids"], ["proj_reading_inventory", "proj_trail_counts"])
        self.assertEqual(len(evidence["claims"]), 3)
        for claim in evidence["claims"]:
            citation, = claim["citations"]
            source = self.facts[citation["id"]]
            self.assertIn(claim["claim_id"], draft.markdown)
            self.assertIn(claim["text"], draft.markdown)
            self.assertEqual(claim["text"], source.assertion)
            self.assertEqual(citation["source"]["sha256"], source.source.sha256)
            self.assertEqual(citation["verification"], "user_supplied")
        self.assertNotIn("Looker", draft.markdown)
        coverage = {row["requirement_id"]: row for row in gaps["requirements"]}
        self.assertEqual(coverage["dashboards"]["coverage"], "partial")
        self.assertEqual(coverage["dashboards"]["named_tool_coverage"], "missing")
        self.assertEqual(coverage["orchestration"]["coverage"], "missing")

    def test_existing_citation_does_not_allow_added_metric_or_tool(self):
        fact = self.facts["fact_inventory_pipeline"]
        for added in (" Reduced costs by 70%.", " Built dbt transformations."):
            with self.subTest(added=added), self.assertRaisesRegex(DraftValidationError, "differs"):
                validate_verbatim_claim(
                    DraftClaim(id="claim_changed", text=fact.assertion + added, evidence_ids=(fact.id,)),
                    self.facts,
                )

    def test_unknown_citation_fails(self):
        with self.assertRaisesRegex(DraftValidationError, "unknown evidence"):
            validate_verbatim_claim(
                DraftClaim(id="claim_missing", text="No evidence.", evidence_ids=("fact_missing",)),
                self.facts,
            )

    def test_empty_library_yields_gap_report_without_claims(self):
        draft = build_draft(self.job, EvidenceLibrary(schema_version="1.0", records=()))
        self.assertIn("No relevant evidence was selected", draft.markdown)
        self.assertEqual(json.loads(draft.evidence_json)["claims"], [])
        self.assertTrue(all(
            requirement["coverage"] == "unknown"
            for requirement in json.loads(draft.gaps_json)["requirements"]
        ))

    def test_cli_stays_offline_and_preserves_existing_output(self):
        env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
        env.update(LANGSMITH_TRACING="true", LANGCHAIN_TRACING_V2="true")
        wrapper = """
import sys
def forbid_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        print("Unexpected network call", file=sys.stderr)
        raise RuntimeError("The draft must be offline")
sys.addaudithook(forbid_network)
from career_agent.cli import main
raise SystemExit(main())
"""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "draft"
            command = [
                sys.executable, "-c", wrapper, "draft", "--job", str(JOB_PATH),
                "--evidence", str(EVIDENCE_PATH), "--output-dir", str(output),
            ]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Unexpected network call", result.stderr)
            self.assertIn("Review status: DRAFT", result.stdout)
            self.assertEqual(
                {path.name for path in output.iterdir()}, {"draft.md", "evidence.json", "gaps.json"}
            )

            original = (output / "draft.md").read_bytes()
            duplicate = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(duplicate.returncode, 1)
            self.assertIn("Output path already exists", duplicate.stderr)
            self.assertEqual((output / "draft.md").read_bytes(), original)
