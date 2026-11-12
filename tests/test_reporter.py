import json
import unittest

from analyzer import AnalysisReport, MigrationAnalyzer
from reporter import format_json, format_text


class ReporterTests(unittest.TestCase):
    def test_json_contains_issue_fields_and_summary(self):
        report = MigrationAnalyzer()._analyze_sql("sample.sql", "DROP TABLE old_table;")
        analysis_report = AnalysisReport(["sample.sql"], report, [])

        data = json.loads(format_json(analysis_report))
        self.assertEqual(data["issues"][0]["file"], "sample.sql")
        self.assertEqual(data["issues"][0]["line"], 1)
        self.assertEqual(data["issues"][0]["risk_score"], 10)
        self.assertEqual(data["summary"]["overall_risk"], "HIGH")

    def test_text_report_includes_finding_and_summary(self):
        issues = MigrationAnalyzer()._analyze_sql("sample.sql", "CREATE INDEX idx ON t(c);")
        output = format_text(AnalysisReport(["sample.sql"], issues, []))
        self.assertIn("CREATE INDEX", output)
        self.assertIn("Overall risk: LOW", output)


if __name__ == "__main__":
    unittest.main()
