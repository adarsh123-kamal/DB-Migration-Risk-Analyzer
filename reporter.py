"""Human-readable and JSON report formatting."""

from __future__ import annotations

import json

from analyzer import AnalysisReport


def format_json(report: AnalysisReport) -> str:
    """Return a stable, indented JSON representation of an analysis report."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def format_text(report: AnalysisReport) -> str:
    """Return a readable terminal report."""
    lines = ["DB Migration Risk Analyzer", "=" * 27]

    if report.files_analyzed:
        lines.append("Files analyzed:")
        lines.extend(f"  - {file_name}" for file_name in report.files_analyzed)
    else:
        lines.append("Files analyzed: none")

    if report.issues:
        lines.extend(("", "Findings:"))
        for issue in report.issues:
            lines.extend(
                (
                    f"[{issue.risk_level}] {issue.file}:{issue.line} - {issue.rule} "
                    f"(score {issue.risk_score})",
                    f"  {issue.explanation}",
                    f"  SQL: {' '.join(issue.statement.split())}",
                )
            )
    else:
        lines.extend(("", "No risky operations detected."))

    summary = report.summary()
    lines.extend(
        (
            "",
            "Summary:",
            f"  Issues: {summary['total_issues']} "
            f"(HIGH: {summary['high']}, MEDIUM: {summary['medium']}, LOW: {summary['low']})",
            f"  Total score: {summary['total_score']}",
            f"  Overall risk: {summary['overall_risk']}",
        )
    )
    if report.errors:
        lines.extend(("", "Errors:"))
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)
