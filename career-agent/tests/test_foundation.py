import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from career_agent.cli import main, WORKSPACE_DIRECTORIES
from career_agent.config import Settings


class FoundationTests(unittest.TestCase):
    def test_status_offline_without_configuration(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["status"]), 0)
        self.assertIn("offline resume drafts", out.getvalue())
        self.assertIsNone(Settings.from_environment({}).openai_api_key)

    def test_settings_hide_secret(self):
        settings = Settings.from_environment({"OPENAI_API_KEY": "private-value", "OPENAI_MODEL": "example"})
        self.assertEqual(settings.openai_model, "example")
        self.assertNotIn("private-value", repr(settings))

    def test_init_is_repeatable_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "person"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["init", "--workspace", str(workspace)]), 0)
                for name in WORKSPACE_DIRECTORIES:
                    self.assertTrue((workspace / name).is_dir())
                original = workspace / "imports" / "existing.txt"
                original.write_text("keep", encoding="utf-8")
                self.assertEqual(main(["init", "--workspace", str(workspace)]), 0)
            self.assertEqual(original.read_text(encoding="utf-8"), "keep")

    def test_init_reports_invalid_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "not-a-directory"
            file.write_text("keep", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                main(["init", "--workspace", str(file)])
            self.assertEqual(result.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
