import tempfile
import unittest
from pathlib import Path

from analyzer import MigrationAnalyzer


class AnalyzerTests(unittest.TestCase):
    def analyze_sql(self, sql: str):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "migration.sql"
            file_path.write_text(sql, encoding="utf-8")
            return MigrationAnalyzer().analyze([file_path])

    def test_detects_each_risk_rule(self):
        sql = """DROP TABLE old_table;
ALTER TABLE users DROP COLUMN old_name;
DELETE FROM users;
TRUNCATE TABLE users;
ALTER TABLE users ALTER COLUMN age TYPE BIGINT;
ALTER TABLE users ADD COLUMN active BOOLEAN NOT NULL;
CREATE INDEX idx_users_name ON users(name);
UPDATE users SET active = TRUE;
"""
        report = self.analyze_sql(sql)
        self.assertEqual(
            {issue.rule for issue in report.issues},
            {
                "DROP TABLE",
                "DROP COLUMN",
                "DELETE without WHERE",
                "TRUNCATE TABLE",
                "ALTER COLUMN TYPE",
                "ADD COLUMN NOT NULL without DEFAULT",
                "CREATE INDEX",
                "UPDATE without WHERE",
            },
        )

    def test_scoped_statements_and_default_are_not_reported(self):
        report = self.analyze_sql(
            "DELETE FROM users WHERE id = 1;\n"
            "UPDATE users SET active = TRUE WHERE id = 1;\n"
            "ALTER TABLE users ADD COLUMN active BOOLEAN NOT NULL DEFAULT FALSE;\n"
            "CREATE TABLE users (id INTEGER);\n"
        )
        self.assertEqual(report.issues, [])

    def test_ignores_comments_and_string_literals(self):
        report = self.analyze_sql(
            "-- DROP TABLE hidden;\n"
            "/* DELETE FROM users; UPDATE users SET a = 1; */\n"
            "INSERT INTO notes(value) VALUES ('TRUNCATE TABLE users; DROP TABLE users;');\n"
        )
        self.assertEqual(report.issues, [])

    def test_line_number_points_to_operation_after_leading_comment(self):
        report = self.analyze_sql("-- note\n\nDROP TABLE old_table;\n")
        self.assertEqual(report.issues[0].line, 3)
        self.assertTrue(report.issues[0].statement.startswith("DROP TABLE"))

    def test_keywords_in_identifiers_are_not_treated_as_dml(self):
        report = self.analyze_sql(
            "CREATE TABLE update_marker (delete VARCHAR(10), update VARCHAR(10));"
        )
        self.assertEqual(report.issues, [])

    def test_statement_splitting_ignores_semicolons_inside_strings(self):
        report = self.analyze_sql(
            "INSERT INTO notes(value) VALUES ('DROP TABLE users;');\nDROP TABLE old_table;"
        )
        self.assertEqual([issue.rule for issue in report.issues], ["DROP TABLE"])
        self.assertEqual(report.issues[0].line, 2)

    def test_directory_analyzes_multiple_sql_files_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.sql").write_text("DROP TABLE one;", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "two.sql").write_text("UPDATE x SET y = 1;", encoding="utf-8")
            (root / "ignore.txt").write_text("DROP TABLE no;", encoding="utf-8")

            report = MigrationAnalyzer().analyze([root])

        self.assertEqual(len(report.files_analyzed), 2)
        self.assertEqual(len(report.issues), 2)

    def test_overlapping_inputs_do_not_duplicate_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration = root / "one.sql"
            migration.write_text("DROP TABLE one;", encoding="utf-8")

            report = MigrationAnalyzer().analyze([root, migration])

        self.assertEqual(len(report.files_analyzed), 1)
        self.assertEqual(len(report.issues), 1)

    def test_empty_file_is_analyzed_without_findings(self):
        report = self.analyze_sql("")
        self.assertEqual(len(report.files_analyzed), 1)
        self.assertEqual(report.issues, [])

    def test_invalid_path_is_reported(self):
        report = MigrationAnalyzer().analyze(["missing-migration.sql"])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("does not exist", report.errors[0])

    def test_risk_scores_and_classification(self):
        report = self.analyze_sql("CREATE INDEX idx ON t(c);\nDROP TABLE old;")
        summary = report.summary()
        self.assertEqual(summary["total_issues"], 2)
        self.assertEqual(summary["high"], 1)
        self.assertEqual(summary["low"], 1)
        self.assertEqual(summary["total_score"], 11)
        self.assertEqual(summary["overall_risk"], "HIGH")


if __name__ == "__main__":
    unittest.main()
