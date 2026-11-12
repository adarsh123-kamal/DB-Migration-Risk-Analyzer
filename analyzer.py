"""Static SQL migration risk analysis."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


RISK_SCORES = {"LOW": 1, "MEDIUM": 5, "HIGH": 10}
RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(frozen=True)
class RiskRule:
    name: str
    risk_level: str
    explanation: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RiskIssue:
    file: str
    line: int
    statement: str
    risk_level: str
    risk_score: int
    rule: str
    explanation: str


@dataclass
class AnalysisReport:
    files_analyzed: list[str]
    issues: list[RiskIssue]
    errors: list[str]

    def summary(self) -> dict[str, int | str]:
        counts = {
            "total_issues": len(self.issues),
            "high": sum(issue.risk_level == "HIGH" for issue in self.issues),
            "medium": sum(issue.risk_level == "MEDIUM" for issue in self.issues),
            "low": sum(issue.risk_level == "LOW" for issue in self.issues),
            "total_score": sum(issue.risk_score for issue in self.issues),
        }
        score = int(counts["total_score"])
        counts["overall_risk"] = (
            "HIGH" if score >= 10 else "MEDIUM" if score >= 5 else "LOW" if score else "NONE"
        )
        return counts

    def to_dict(self) -> dict[str, object]:
        return {
            "files_analyzed": self.files_analyzed,
            "issues": [
                {
                    "file": issue.file,
                    "line": issue.line,
                    "statement": issue.statement,
                    "risk_level": issue.risk_level,
                    "risk_score": issue.risk_score,
                    "rule": issue.rule,
                    "explanation": issue.explanation,
                }
                for issue in self.issues
            ],
            "summary": self.summary(),
            "errors": self.errors,
        }


RULES = (
    RiskRule(
        "DROP TABLE",
        "HIGH",
        "Permanently removes an entire database table.",
        re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    ),
    RiskRule(
        "DROP COLUMN",
        "HIGH",
        "Removes a column and may cause data loss.",
        re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    ),
    RiskRule(
        "DELETE without WHERE",
        "HIGH",
        "May delete all rows from a table.",
        re.compile(r"^\s*DELETE\b", re.IGNORECASE),
    ),
    RiskRule(
        "TRUNCATE TABLE",
        "HIGH",
        "Removes all rows from a table.",
        re.compile(r"\bTRUNCATE\s+(?:TABLE\b)?", re.IGNORECASE),
    ),
    RiskRule(
        "ALTER COLUMN TYPE",
        "MEDIUM",
        "Changing a column type may cause data conversion issues.",
        re.compile(
            r"\bALTER\s+COLUMN\b[\s\S]*?\b(?:TYPE\b|SET\s+DATA\s+TYPE\b)",
            re.IGNORECASE,
        ),
    ),
    RiskRule(
        "ADD COLUMN NOT NULL without DEFAULT",
        "MEDIUM",
        "Existing records may not satisfy the new constraint.",
        re.compile(r"\bADD\s+(?:COLUMN\b)?[\s\S]*?\bNOT\s+NULL\b", re.IGNORECASE),
    ),
    RiskRule(
        "CREATE INDEX",
        "LOW",
        "Index creation may affect performance during deployment.",
        re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    ),
    RiskRule(
        "UPDATE without WHERE",
        "HIGH",
        "May modify every row in a table.",
        re.compile(r"^\s*UPDATE\b", re.IGNORECASE),
    ),
)


def _blank_non_code(sql: str) -> str:
    """Mask comments, string literals, and quoted identifiers without shifting positions."""
    masked = list(sql)
    length = len(sql)
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, end):
            if sql[position] not in "\r\n":
                masked[position] = " "

    while index < length:
        if sql.startswith("--", index):
            end = index + 2
            while end < length and sql[end] not in "\r\n":
                end += 1
            blank(index, end)
            index = end
        elif sql.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            blank(start, index)
        elif sql[index] == "'":
            start = index
            index += 1
            while index < length:
                if sql[index] == "\\" and index + 1 < length:
                    index += 2
                elif sql[index] == "'":
                    if index + 1 < length and sql[index + 1] == "'":
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            blank(start, index)
        elif sql[index] in ('"', "`", "["):
            opener = sql[index]
            closer = "]" if opener == "[" else opener
            start = index
            index += 1
            while index < length:
                if sql[index] == closer:
                    if index + 1 < length and sql[index + 1] == closer:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            blank(start, index)
        elif sql[index] == "$":
            delimiter = re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", sql[index:])
            if delimiter:
                tag = delimiter.group(0)
                end_tag = sql.find(tag, index + len(tag))
                end = length if end_tag < 0 else end_tag + len(tag)
                blank(index, end)
                index = end
            else:
                index += 1
        else:
            index += 1
    return "".join(masked)


def _statement_spans(sql: str, masked: str) -> Iterable[tuple[int, int]]:
    start = 0
    for index, character in enumerate(masked):
        if character == ";":
            yield start, index + 1
            start = index + 1
    if start < len(sql):
        yield start, len(sql)


class MigrationAnalyzer:
    """Analyze SQL files for a small, explicit set of potentially risky operations."""

    def analyze(self, paths: Sequence[str | Path]) -> AnalysisReport:
        files: list[Path] = []
        errors: list[str] = []
        for supplied_path in paths:
            path = Path(supplied_path)
            if not path.exists():
                errors.append(f"{path}: path does not exist")
            elif path.is_dir():
                files.extend(sorted(path.rglob("*.sql"), key=lambda item: str(item).casefold()))
            elif path.is_file():
                files.append(path)
            else:
                errors.append(f"{path}: not a regular file or directory")

        analyzed: list[str] = []
        issues: list[RiskIssue] = []
        seen_files: set[str] = set()
        for file_path in files:
            identity = os.path.normcase(str(file_path.resolve()))
            if identity in seen_files:
                continue
            seen_files.add(identity)
            display_path = str(file_path)
            try:
                sql = file_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as error:
                errors.append(f"{display_path}: could not read file ({error})")
                continue
            analyzed.append(display_path)
            issues.extend(self._analyze_sql(display_path, sql))

        issues.sort(key=lambda issue: (issue.file.casefold(), issue.line, issue.rule))
        return AnalysisReport(analyzed, issues, errors)

    def _analyze_sql(self, file_name: str, sql: str) -> list[RiskIssue]:
        masked = _blank_non_code(sql)
        issues: list[RiskIssue] = []
        for start, end in _statement_spans(sql, masked):
            masked_statement = masked[start:end]
            first_code = next(
                (offset for offset, character in enumerate(masked_statement) if not character.isspace()),
                None,
            )
            if first_code is None:
                continue

            original_statement = sql[start + first_code : end].strip()
            line = sql.count("\n", 0, start + first_code) + 1
            has_where = re.search(r"\bWHERE\b", masked_statement, re.IGNORECASE) is not None
            has_default = re.search(r"\bDEFAULT\b", masked_statement, re.IGNORECASE) is not None

            for rule in RULES:
                if not rule.pattern.search(masked_statement):
                    continue
                if rule.name in ("DELETE without WHERE", "UPDATE without WHERE") and has_where:
                    continue
                if rule.name == "ADD COLUMN NOT NULL without DEFAULT" and has_default:
                    continue
                issues.append(
                    RiskIssue(
                        file=file_name,
                        line=line,
                        statement=original_statement,
                        risk_level=rule.risk_level,
                        risk_score=RISK_SCORES[rule.risk_level],
                        rule=rule.name,
                        explanation=rule.explanation,
                    )
                )
        return issues
