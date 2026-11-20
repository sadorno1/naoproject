import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import setup_keys


class SetupKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"

    def test_create_and_replace_preserves_other_settings_and_removes_duplicate_keys(self):
        self.path.write_text('#Keep this\nOTHER_SETTING=unchanged\nOPENAI_API_KEY=old\nexport OPENAI_API_KEY=duplicate\n')
        setup_keys.save_key(self.path, "sk-test-dummy_123")
        text = self.path.read_text()
        self.assertIn("#Keep this\nOTHER_SETTING=unchanged\n", text)
        self.assertEqual(text.count("OPENAI_API_KEY="), 1)
        self.assertIn("OPENAI_API_KEY=sk-test-dummy_123", text)

    def test_new_file_can_be_written_without_dependencies(self):
        setup_keys.save_key(self.path, "sk-test-dummy")
        self.assertEqual(self.path.read_text(), "OPENAI_API_KEY=sk-test-dummy\n")

    def test_invalid_input_does_not_modify_existing_file(self):
        self.path.write_text("OTHER_SETTING=unchanged\n")
        for value in ("", "sk-key\nINJECTED=value", "OPENAI_API_KEY=sk-key", "'sk-key'"):
            with self.assertRaises(ValueError):
                setup_keys.save_key(self.path, value)
            self.assertEqual(self.path.read_text(), "OTHER_SETTING=unchanged\n")

    def test_setup_never_prints_key(self):
        output = io.StringIO()
        with patch.object(setup_keys, "ENV_PATH", self.path), patch("getpass.getpass", return_value="sk-secret-test-only"), contextlib.redirect_stdout(output):
            self.assertEqual(setup_keys.main([]), 0)
        self.assertNotIn("sk-secret-test-only", output.getvalue())
        self.assertTrue(self.path.exists())

    def test_blank_input_does_not_create_file(self):
        with patch.object(setup_keys, "ENV_PATH", self.path), patch("getpass.getpass", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup_keys.main([]), 0)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
