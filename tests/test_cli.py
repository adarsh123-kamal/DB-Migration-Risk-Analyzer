import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from main import main


class CliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(arguments)
        return status, output.getvalue()

    def test_exit_code_for_invalid_path(self):
        status, output = self.run_cli(["analyze", "not-a-real-file.sql"])
        self.assertEqual(status, 2)
        self.assertIn("does not exist", output)

    def test_fail_on_high_returns_nonzero_only_when_threshold_met(self):
        with tempfile.TemporaryDirectory() as directory:
            sql_file = Path(directory) / "risk.sql"
            sql_file.write_text("DROP TABLE users;", encoding="utf-8")
            self.assertEqual(self.run_cli(["analyze", str(sql_file), "--fail-on", "high"])[0], 1)
            self.assertEqual(self.run_cli(["analyze", str(sql_file), "--fail-on", "low"])[0], 1)

            safe_file = Path(directory) / "safe.sql"
            safe_file.write_text("SELECT 1;", encoding="utf-8")
            self.assertEqual(self.run_cli(["analyze", str(safe_file), "--fail-on", "high"])[0], 0)

    def test_json_output_file_is_generated(self):
        with tempfile.TemporaryDirectory() as directory:
            sql_file = Path(directory) / "risk.sql"
            report_file = Path(directory) / "report.json"
            sql_file.write_text("DROP TABLE users;", encoding="utf-8")

            status, _ = self.run_cli(
                ["analyze", str(sql_file), "--output", str(report_file), "--fail-on", "high"]
            )

            self.assertEqual(status, 1)
            data = json.loads(report_file.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["high"], 1)

    def test_explicit_json_format_is_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            sql_file = Path(directory) / "safe.sql"
            sql_file.write_text("SELECT 1;", encoding="utf-8")
            status, output = self.run_cli(["analyze", str(sql_file), "--format", "json"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["summary"]["total_issues"], 0)


if __name__ == "__main__":
    unittest.main()
