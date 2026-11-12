import csv
import io
import json
import unittest

from analyzer import AnalysisReport, MigrationAnalyzer
from dashboard import aggregate_reports, build_csv_report, build_findings_dataframe


class DashboardReportTests(unittest.TestCase):
    def setUp(self):
        issues = MigrationAnalyzer()._analyze_sql(
            "migration.sql",
            "DROP TABLE archived_orders;\nCREATE INDEX idx_orders_date ON orders(created_at);",
        )
        self.report = AnalysisReport(["migration.sql"], issues, [])

    def test_findings_dataframe_contains_dashboard_columns(self):
        findings = build_findings_dataframe(self.report)
        self.assertEqual(list(findings.columns), [
            "File Name",
            "Line Number",
            "Risk Level",
            "Rule Name",
            "Risk Score",
            "SQL Statement",
            "Explanation",
        ])
        self.assertEqual(findings.iloc[0]["Risk Level"], "HIGH")

    def test_csv_report_includes_summary_and_findings(self):
        rows = list(csv.DictReader(io.StringIO(build_csv_report(self.report))))
        self.assertEqual(rows[0]["Record Type"], "SUMMARY")
        self.assertEqual(rows[0]["Files Analyzed"], "1")
        self.assertEqual(rows[0]["Total Findings"], "2")
        self.assertEqual(rows[1]["Record Type"], "FINDING")
        self.assertEqual(rows[1]["File Name"], "migration.sql")
        self.assertEqual(rows[1]["Risk Level"], "HIGH")

    def test_aggregate_reports_combines_findings_and_unique_files(self):
        combined = aggregate_reports(
            {
                "first": self.report,
                "second": AnalysisReport(["second.sql"], [], ["sample warning"]),
            }
        )
        self.assertEqual(combined.files_analyzed, ["migration.sql", "second.sql"])
        self.assertEqual(len(combined.issues), 2)
        self.assertEqual(combined.errors, ["sample warning"])

    def test_json_report_from_existing_reporter_is_valid(self):
        from reporter import format_json

        payload = json.loads(format_json(self.report))
        self.assertEqual(payload["summary"]["total_issues"], 2)
        self.assertEqual(payload["issues"][0]["file"], "migration.sql")


if __name__ == "__main__":
    unittest.main()
