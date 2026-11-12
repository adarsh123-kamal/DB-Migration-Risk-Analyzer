"""Command-line entry point for the migration risk analyzer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from analyzer import MigrationAnalyzer, RISK_ORDER
from reporter import format_json, format_text


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find potentially risky operations in SQL migration files."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="analyze a SQL file or a directory of SQL files")
    analyze.add_argument("path", help="SQL file or directory (directories are searched recursively)")
    analyze.add_argument("--format", choices=("text", "json"), help="report format")
    analyze.add_argument("--output", help="write the report to this file")
    analyze.add_argument(
        "--fail-on",
        choices=("low", "medium", "high"),
        help="return exit code 1 if any finding is at least this severity",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = MigrationAnalyzer().analyze([args.path])
    output_format = args.format or (
        "json" if args.output and Path(args.output).suffix.lower() == ".json" else "text"
    )
    rendered = format_json(report) if output_format == "json" else format_text(report)

    if args.output:
        try:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        except OSError as error:
            print(f"Error: could not write report to {args.output}: {error}", file=sys.stderr)
            return 2

    print(rendered)
    if report.errors:
        return 2
    if args.fail_on and any(
        RISK_ORDER[issue.risk_level] >= RISK_ORDER[args.fail_on.upper()]
        for issue in report.issues
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
