import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

from career_agent.contracts import DraftClaim, EvidenceLibrary, JobSnapshot, validate_claim_references
from career_agent.matching import match

EXAMPLES = Path(__file__).resolve().parents[1] / "data" / "examples"
JOB = EXAMPLES / "harbor-demo-job.json"
EVIDENCE = EXAMPLES / "harbor-demo-evidence.json"


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.job = JobSnapshot.model_validate_json(JOB.read_bytes())
        self.library = EvidenceLibrary.model_validate_json(EVIDENCE.read_bytes())

    def test_expected_ranking_and_distinct_tool_gap(self):
        report = match(self.job, self.library)
        self.assertEqual([(row.record_id, row.score) for row in report.ranked_records], [
            ("proj_reading_inventory", 12), ("proj_trail_counts", 4),
        ])
        self.assertEqual(report.ranked_records[0].direct_requirement_ids, ("sql", "pipelines"))
        self.assertEqual(report.ranked_records[0].partial_requirement_ids, ("dashboards",))
        by_id = {item.requirement_id: item for item in report.requirements}
        self.assertEqual(by_id["dashboards"].coverage, "partial")
        self.assertEqual(by_id["dashboards"].named_tool_coverage, "missing")
        self.assertEqual(by_id["dashboards"].capability_evidence_ids, ("fact_inventory_dashboard",))
        self.assertEqual(by_id["orchestration"].coverage, "missing")

    def test_tool_must_support_the_capability_in_the_same_fact(self):
        data = self.library.model_dump(mode="json")
        inventory = next(record for record in data["records"] if record["id"] == "proj_reading_inventory")
        inventory["facts"][0]["technologies"].append("Looker")
        report = match(self.job, EvidenceLibrary.model_validate(data))
        self.assertEqual(report.requirements[2].coverage, "partial")
        inventory["facts"][1]["technologies"].append("  lOoKer  ")
        report = match(self.job, EvidenceLibrary.model_validate(data))
        self.assertEqual(report.requirements[2].coverage, "direct")
        self.assertEqual(report.requirements[2].named_tool_evidence_ids, ("fact_inventory_dashboard",))

    def test_ties_sort_by_id_regardless_of_input_order(self):
        data = self.library.model_dump(mode="json")
        trail = data["records"][0]
        second = {**trail, "id": "proj_a_trends", "facts": [
            {**trail["facts"][0], "id": "fact_other_trends"},
        ]}
        data["records"].append(second)
        first_report = match(self.job, EvidenceLibrary.model_validate(data))
        data["records"].reverse()
        self.assertEqual(first_report, match(self.job, EvidenceLibrary.model_validate(data)))
        self.assertEqual(
            [row.record_id for row in first_report.ranked_records[1:]],
            ["proj_a_trends", "proj_trail_counts"],
        )

    def test_empty_library_reports_unknown(self):
        empty = EvidenceLibrary(schema_version="1.0", records=())
        report = match(self.job, empty)
        self.assertEqual(report.ranked_records, ())
        self.assertTrue(all(item.coverage == "unknown" for item in report.requirements))
        self.assertEqual(report.requirements[2].named_tool_coverage, "unknown")

    def test_snapshot_quote_and_evidence_identity_are_validated(self):
        job = self.job.model_dump(mode="json")
        job["requirements"][0]["source_phrase"] = "This did not appear in the source."
        with self.assertRaisesRegex(ValidationError, "must quote the job description"):
            JobSnapshot.model_validate(job)
        job = self.job.model_dump(mode="json")
        job["requirements"][1]["id"] = job["requirements"][0]["id"]
        with self.assertRaisesRegex(ValidationError, "Duplicate requirement"):
            JobSnapshot.model_validate(job)
        library = self.library.model_dump(mode="json")
        library["records"][1]["facts"][0]["id"] = library["records"][0]["facts"][0]["id"]
        with self.assertRaisesRegex(ValidationError, "Duplicate evidence"):
            EvidenceLibrary.model_validate(library)

    def test_fixture_sources_are_reproducible(self):
        for record in self.library.records:
            for fact in record.facts:
                source = (EXAMPLES / fact.source.reference).read_bytes()
                self.assertIn(fact.assertion, source.decode("utf-8"))
                self.assertEqual(fact.source.sha256, hashlib.sha256(source).hexdigest())
        self.assertEqual(
            self.job.description_sha256,
            hashlib.sha256(self.job.description.encode("utf-8")).hexdigest(),
        )

    def test_claim_references_require_real_evidence_ids(self):
        claim = DraftClaim(id="claim_inventory", text="Queried SQLite.", evidence_ids=("fact_inventory_pipeline",))
        validate_claim_references(claim, self.library)
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_claim_references(
                DraftClaim(id="claim_unknown", text="Reduced costs.", evidence_ids=("fact_imagined",)),
                self.library,
            )

    def test_cli_matches_without_key_and_reports_invalid_input(self):
        env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
        command = [
            sys.executable, "-m", "career_agent.cli", "match", "--job", str(JOB), "--evidence",
        ]
        result = subprocess.run([*command, str(EVIDENCE)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["ranked_records"][0]["record_id"], "proj_reading_inventory")

        invalid = subprocess.run([*command, str(JOB)], env=env, capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, "")
        self.assertIn("Invalid evidence JSON", invalid.stderr)
        self.assertNotIn("Harbor Lantern Labs", invalid.stderr)
