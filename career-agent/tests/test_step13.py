import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from career_agent.cli import main
from career_agent.contracts import EvidenceLibrary, JobSnapshot
from career_agent.documents import read_document
from career_agent.drafting import DraftValidationError, build_draft
from career_agent.importing import ProposedEvidence, ProposedJob, import_evidence, import_job
from career_agent.model import ModelError, ask
from career_agent.model_selection import Selection
from career_agent.storage import history


EXAMPLES = Path(__file__).resolve().parents[1] / "data" / "examples"
JOB = EXAMPLES / "harbor-demo-job.json"
EVIDENCE = EXAMPLES / "harbor-demo-evidence.json"


class ImportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.notes = self.root / "project.txt"
        self.notes.write_text("Built a SQL pipeline.\n", encoding="utf-8")
        self.proposal = ProposedEvidence.model_validate({"records": [{
            "title": "Pipeline", "kind": "project", "facts": [{
                "assertion": "Built a SQL pipeline.", "capabilities": ["SQL"], "technologies": ["SQL"],
            }],
        }]})

    def test_import_matches_sources_and_reuses_unmodified_library(self):
        with patch("career_agent.importing.ask", return_value=self.proposal) as model:
            library_path = self.root / "evidence.json"
            with redirect_stdout(StringIO()):
                code = main([
                    "import-evidence", "--use-openai", "--source", str(self.notes),
                    "--output", str(library_path),
                ])
            self.assertEqual(code, 0)
            original = EvidenceLibrary.model_validate_json(library_path.read_bytes())
            self.assertEqual(import_evidence([self.notes], original), original)
        model.assert_called_once()
        self.assertNotIn(str(self.notes), str(model.call_args))
        fact = original.records[0].facts[0]
        self.assertEqual(fact.verification, "user_supplied")
        self.assertEqual(fact.source.sha256, hashlib.sha256(self.notes.read_bytes()).hexdigest())
        self.assertEqual(fact.source.reference, str(self.notes.resolve()))

    def test_refresh_updates_only_the_changed_source(self):
        another = self.root / "another.txt"
        another.write_bytes(self.notes.read_bytes())
        with patch("career_agent.importing.ask", return_value=self.proposal):
            original = import_evidence([self.notes, another], None)
        self.notes.write_text("Built a SQL pipeline. Added file validation.", encoding="utf-8")
        with patch("career_agent.importing.ask", return_value=self.proposal) as model:
            refreshed = import_evidence([self.notes], original)
        model.assert_called_once()
        self.assertEqual(len(refreshed.records), 2)
        self.assertIn(original.records[1], refreshed.records)
        new_fact = refreshed.records[1].facts[0]
        self.assertEqual(new_fact.id, original.records[0].facts[0].id)
        self.assertNotEqual(new_fact.source.sha256, original.records[0].facts[0].source.sha256)

    def test_evidence_rejects_invented_wording_and_tool_labels(self):
        fact = self.proposal.records[0].facts[0]
        with patch("career_agent.importing.ask", return_value=self.proposal):
            fact.assertion = "Built a SQL pipeline and saved 90%."
            with self.assertRaisesRegex(ModelError, "quotation is missing"):
                import_evidence([self.notes], None)
            fact.assertion = "Built a SQL pipeline."
            fact.technologies = ["Airflow"]
            with self.assertRaisesRegex(ModelError, "technology is missing"):
                import_evidence([self.notes], None)

    def test_job_keeps_raw_posting_and_validates_requirement_quote(self):
        path = EXAMPLES / "harbor-demo-posting.txt"
        proposal = ProposedJob.model_validate({
            "single_posting": True, "employer": "Harbor Lantern Labs",
            "title": "Data Operations Associate", "location": None,
            "requirements": [{
                "capability": "SQL", "level": "required", "named_tools": [],
                "source_phrase": "Use SQL to query operational data.",
            }],
        })
        with patch("career_agent.importing.ask", return_value=proposal):
            job = import_job(path, "job_harbor", 1, None)
            self.assertEqual(job.description, path.read_text(encoding="utf-8"))
            proposal.requirements[0].source_phrase = "Required AWS experience."
            with self.assertRaisesRegex(ModelError, "quotation is missing"):
                import_job(path, "job_harbor", 1, None)
            proposal.single_posting = False
            with self.assertRaisesRegex(ModelError, "exactly one"):
                import_job(path, "job_harbor", 1, None)


class ModelDraftTests(unittest.TestCase):
    def test_model_selection_approves_offline_and_exports_docx(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            workspace = Path(temporary)
            draft = workspace / "review"
            inputs = ["--job", str(JOB), "--evidence", str(EVIDENCE)]
            with patch("career_agent.model_selection.ask", return_value=Selection(
                selected_fact_ids=["fact_inventory_dashboard"],
            )) as model:
                self.assertEqual(main([
                    "draft", *inputs, "--use-openai", "--output-dir", str(draft),
                ]), 0)
            model.assert_called_once()
            bundle = json.loads((draft / "evidence.json").read_bytes())
            self.assertEqual(len(bundle["claims"]), 1)
            self.assertEqual(bundle["selected_fact_ids"], ["fact_inventory_dashboard"])
            with patch("career_agent.model_selection.ask", side_effect=AssertionError("offline approval")):
                self.assertEqual(main([
                    "approve", *inputs, "--draft-dir", str(draft), "--workspace", str(workspace),
                ]), 0)
            self.assertEqual(history(workspace)[0]["resume_id"], bundle["draft_id"])

            if importlib.util.find_spec("docx"):
                from docx import Document

                output = workspace / "resume.docx"
                self.assertEqual(main([
                    "export-docx", "--workspace", str(workspace), "--resume", bundle["draft_id"],
                    "--output", str(output),
                ]), 0)
                text = "\n".join(item.text for item in Document(BytesIO(output.read_bytes())).paragraphs)
                self.assertIn("Published an inventory dashboard using a spreadsheet.", text)
                self.assertNotIn("claim_fact_", text)
                original = output.read_bytes()
                with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                    main([
                        "export-docx", "--workspace", str(workspace), "--resume", bundle["draft_id"],
                        "--output", str(output),
                    ])
                self.assertEqual(output.read_bytes(), original)

    def test_fact_selection_rejects_outside_shortlist_and_duplicates(self):
        job = JobSnapshot.model_validate_json(JOB.read_bytes())
        library = EvidenceLibrary.model_validate_json(EVIDENCE.read_bytes())
        for ids in [
            ("fact_audio_entries",),
            ("fact_inventory_pipeline", "fact_inventory_pipeline"),
        ]:
            with self.subTest(ids=ids), self.assertRaisesRegex(DraftValidationError, "ranked shortlist"):
                build_draft(job, library, ids)

    def test_requires_explicit_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(ModelError, "Set OPENAI_API_KEY"):
                ask(Selection, "Select evidence", {})

    @unittest.skipUnless(importlib.util.find_spec("openai"), "model extra not installed")
    def test_responses_request_has_opt_in_privacy_settings(self):
        import httpx
        from openai import OpenAI

        def respond(request):
            self.assertEqual(request.url.path, "/v1/responses")
            payload = json.loads(request.content)
            self.assertIs(payload["store"], False)
            self.assertEqual(payload["model"], "example-model")
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            self.assertNotIn("tools", payload)
            return httpx.Response(200, json={
                "id": "resp_test", "object": "response", "status": "completed", "output": [{
                    "type": "message", "role": "assistant", "id": "msg_test", "status": "completed",
                    "content": [{"type": "output_text", "text": '{"selected_fact_ids":["fact_demo"]}', "annotations": []}],
                }],
            })

        client = OpenAI(api_key="fake", http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        with patch("openai.OpenAI", return_value=client), patch.dict(os.environ, {
            "OPENAI_API_KEY": "fake", "OPENAI_MODEL": "example-model",
        }):
            self.assertEqual(ask(Selection, "Select evidence", {}).selected_fact_ids, ["fact_demo"])

    @unittest.skipUnless(importlib.util.find_spec("docx"), "documents extra not installed")
    def test_local_docx_extraction_reads_paragraphs_and_tables(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "resume.docx"
            document = Document()
            document.add_paragraph("Built a pipeline.")
            document.add_table(rows=1, cols=1).cell(0, 0).text = "Used SQL."
            document.save(path)
            _, text = read_document(path)
            self.assertEqual(text, "Built a pipeline.\nUsed SQL.")

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "documents extra not installed")
    def test_text_pdf_extraction_reads_the_posting(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "posting.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=200, height=200)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }),
                }),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 100 Td (Use SQL.) Tj ET")
            page.replace_contents(stream)
            writer.write(path)
            _, text = read_document(path)
            self.assertIn("Use SQL.", text)
