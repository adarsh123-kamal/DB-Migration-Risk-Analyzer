# DB Migration Risk Analyzer

A Python developer tool that statically scans SQL migration files for potentially risky schema and data changes. Use its command-line interface for local and CI checks, or its interactive Streamlit dashboard for charts, filtering, and downloadable reports.

> This tool highlights selected risks; it does not prove a migration is safe or unsafe. Review findings in the context of your database, data, and deployment plan.

## Problem statement

Database migrations can remove data, alter every row, or impose constraints that existing records do not satisfy. These operations are easy to miss during code review. This analyzer adds a small, repeatable pre-deployment check to local workflows and CI.

## Motivation

The project demonstrates practical developer tooling: parsing files, applying static checks, reporting useful locations, writing JSON, testing command-line behavior, and integrating a quality check into GitHub Actions.

## Features

- Analyze a SQL file or recursively scan `.sql` files in a directory.
- Detect the eight operations listed below while ignoring comments, quoted strings, and quoted identifiers.
- Report the file, line, SQL text, rule, severity, score, and explanation.
- Print a readable report or emit JSON to stdout or a file.
- Return non-zero statuses for invalid input and configurable risk thresholds.
- Explore results in a dark Streamlit dashboard with interactive Plotly charts and filters.
- Upload SQL migrations or analyze the included sample files without executing SQL.
- Download combined JSON, CSV, and text reports.

## Technology stack

Python 3.12+, SQL, `argparse`, `re`, `json`, `unittest`, Streamlit, Plotly, Pandas, GitHub Actions, and Git.

## Architecture

- `analyzer.py` masks comments and quoted content without changing offsets, splits SQL at unquoted semicolons, applies explicit risk rules, and builds the report data.
- `reporter.py` formats the report as readable text or JSON.
- `main.py` parses arguments, writes optional report files, and maps input errors and risk thresholds to exit codes.
- `dashboard.py` reuses `MigrationAnalyzer` and `reporter.py`; uploaded files are passed through temporary files, and session state retains results across dashboard pages.
- `.streamlit/config.toml` applies the dark dashboard theme.
- `tests/` verifies the rules, scanner behavior, reporting, file handling, and CLI results.

## Project structure

```text
DB-Migration-Risk-Analyzer/
├── analyzer.py
├── main.py
├── reporter.py
├── dashboard.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
├── test_files/
│   ├── safe_migration.sql
│   ├── risky_migration.sql
│   └── mixed_migration.sql
├── tests/
│   ├── test_analyzer.py
│   ├── test_reporter.py
│   ├── test_cli.py
│   └── test_dashboard.py
└── .github/
    └── workflows/
        └── ci.yml
```

## Installation (Windows)

Install Python 3.12 and ensure the Python Launcher (`py`) is available. In PowerShell, move into the project directory and optionally create an isolated environment:

```powershell
cd "C:\path\to\DB Migration Risk Analyzer"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3.12 --version
```

Install the dashboard dependencies from the project root:

```powershell
py -3.12 -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, you can still run the `py -3.12` commands without activating `.venv`.

## Usage

Run commands from the project root:

```powershell
py -3.12 main.py analyze test_files\safe_migration.sql
py -3.12 main.py analyze test_files\
py -3.12 main.py analyze test_files\mixed_migration.sql --format json
py -3.12 main.py analyze test_files\risky_migration.sql --output report.json
py -3.12 main.py analyze test_files\risky_migration.sql --fail-on high
```

## Dashboard

Run the interactive dashboard from the project root:

```powershell
py -3.12 -m streamlit run dashboard.py
```

Streamlit starts a local server and opens the dashboard in your browser. The sidebar provides page navigation, multi-file `.sql` upload, sample selection, a per-file size limit, severity filtering, and an Analyze action. On **Migration Analysis**, select uploaded and/or sample files, then press **Analyze selected files**. Results are retained in the current Streamlit session as you navigate; analyzing a source again updates that source's result, and **Clear analyzed results** clears the session.

### Deploy on Streamlit Community Cloud

The repository is arranged for Community Cloud: `dashboard.py`, `requirements.txt`, `.streamlit/config.toml`, and `test_files/` are at the repository root. In Streamlit Community Cloud, create or redeploy the app with:

- Repository: `adarsh123-kamal/DB-Migration-Risk-Analyzer`
- Branch: `main`
- Main file path: `dashboard.py`
- Python version: `3.12`

Keep `server.headless` unset in `.streamlit/config.toml`. Streamlit automatically selects headless mode on Linux hosts without a display and opens a browser by default on a local Windows run. The app does not set a fixed server port; Community Cloud can use its expected port. After pushing a config change, use **Reboot app** in Community Cloud and inspect the startup traceback if the health check still fails.

The **Overview** page shows file/finding metrics and interactive severity, file, and rule charts. **Risk Findings** supports severity/rule filters, text search, and sorting. On **Reports**, download the current combined report as JSON, CSV, or TXT. JSON is generated with the existing reporter; CSV contains a summary record followed by individual finding records.

Uploads are limited to `.sql` files and the configured maximum size (10 MB by default, adjustable in the sidebar up to 25 MB). The upload is written to a temporary directory for the existing path-based analyzer and removed after analysis. An empty upload is reported as an error. The application does not execute uploaded or sample SQL.

### Screenshots

Screenshot placeholders for a portfolio README:

- Overview: `docs/screenshots/dashboard-overview.png`
- Risk findings: `docs/screenshots/dashboard-findings.png`

Capture these pages in your own environment and add the images at those paths if desired.

### CLI options

```text
py -3.12 main.py analyze <SQL-file-or-directory>
  --format {text,json}   Select stdout and report-file format.
  --output PATH          Write the same report to PATH; a .json suffix selects JSON unless --format is given.
  --fail-on {low,medium,high}
                         Exit 1 if any issue is at least this severity.
```

Exit codes: `0` means analysis completed below the requested threshold; `1` means the `--fail-on` threshold was met; `2` means an input or report-output error occurred. If a directory contains no SQL files, it returns an empty report. Empty readable files are valid inputs.

## Detection rules

| Rule | Severity | Explanation |
|---|---|---|
| `DROP TABLE` | HIGH | Permanently removes an entire database table. |
| `DROP COLUMN` | HIGH | Removes a column and may cause data loss. |
| `DELETE` without `WHERE` | HIGH | May delete all rows from a table. |
| `TRUNCATE TABLE` | HIGH | Removes all rows from a table. |
| `ALTER COLUMN TYPE` | MEDIUM | Changing a column type may cause data conversion issues. |
| `ADD COLUMN NOT NULL` without `DEFAULT` | MEDIUM | Existing records may not satisfy the new constraint. |
| `CREATE INDEX` | LOW | Index creation may affect performance during deployment. |
| `UPDATE` without `WHERE` | HIGH | May modify every row in a table. |

Comments (`--` and `/* ... */`), single-quoted strings, and quoted identifiers are masked before matching. SQL statement boundaries and line positions are preserved, so dangerous-looking text inside those regions is not treated as an operation.

## Risk scoring methodology

Each finding gets a fixed weight: LOW = 1, MEDIUM = 5, HIGH = 10. The total migration score is the **sum** of all finding weights, so multiple findings accumulate. The overall classification uses that total: `NONE` for 0, `LOW` for 1–4, `MEDIUM` for 5–9, and `HIGH` for 10 or more. Severity counts are also shown separately. The `--fail-on` option is based on the severity of individual findings, not the summed score.

## Sample output

```text
DB Migration Risk Analyzer
===========================
Files analyzed:
  - test_files\risky_migration.sql

Findings:
[HIGH] test_files\risky_migration.sql:3 - DROP TABLE (score 10)
  Permanently removes an entire database table.
  SQL: DROP TABLE archived_orders;

Summary:
  Issues: 8 (HIGH: 5, MEDIUM: 2, LOW: 1)
  Total score: 61
  Overall risk: HIGH
```

Exact line numbers and counts depend on the input file.

## Testing

Run the full test suite (the analyzer and CLI use the standard library; the dashboard uses the dependencies in `requirements.txt`):

```powershell
py -3.12 -m unittest discover -s tests -v
```

The tests cover all eight rules, safe statements, comments and literals, line numbers, recursive multi-file analysis, JSON/text reports, risk aggregation, invalid paths, CLI exit behavior, and dashboard report aggregation/CSV output.

## CI/CD

`.github/workflows/ci.yml` runs for pushes and pull requests. It sets up Python 3.12, installs the dashboard dependencies from `requirements.txt`, smoke-tests the Streamlit server on an Ubuntu runner, runs unit tests, analyzes the safe sample, and verifies that the risky sample returns exit code 1 with `--fail-on high`. The threshold check is expected to return 1; the workflow itself succeeds when that behavior is observed.

## Limitations

- This is a static analyzer with a deliberately small set of pattern-based rules, not a SQL parser. SQL dialects, procedural SQL, CTEs, unusual formatting, and multi-action `ALTER TABLE` statements may not be interpreted precisely.
- `WHERE` detection is lexical and statement-wide. More complex SQL structure can create false positives or false negatives.
- The analyzer does not connect to a database, inspect live schema/data, estimate locks or runtime, or verify rollback and deployment strategies.
- Index build behavior and type-conversion safety depend on the database engine and its version.
- A finding is a review signal, not a guarantee of migration safety; absence of findings is not a safety guarantee.
- Dashboard results are held in the active Streamlit session and are not a persistent shared database or audit log.
- Large uploads are capped by the dashboard setting; a user's browser/session should not be used to upload sensitive production data without an appropriate privacy review.

## Future enhancements

- Add dialect-aware parsing and configurable rules.
- Detect more operational risks, such as lock-heavy changes and table rewrites, with engine-specific context.
- Support baseline/allow-list files and richer CI annotations.
- Add machine-readable severity thresholds and report summaries for changed files.

## GitHub repository description

`Python CLI for static SQL migration risk detection, line-numbered reports, JSON output, and CI threshold checks.`

## Resume-ready project description

- Built a Python CLI for static SQL migration analysis that detects destructive and potentially disruptive schema/data operations and reports line-numbered findings.
- Implemented text and JSON reporting, additive severity scoring, input validation, and configurable exit thresholds for CI-friendly migration checks.
- Added focused `unittest` coverage for SQL comments and literals, rule detection, multi-file input, reporting, and command-line behavior; integrated tests and sample checks with GitHub Actions.
- Extended the analyzer with a Streamlit dashboard featuring interactive Plotly risk analytics, filtered findings, multi-file uploads, and downloadable JSON/CSV/TXT reports while reusing the existing analysis engine.

## Uploading to GitHub

Create an empty repository on GitHub (do not initialize it with a README if you plan to push this existing README). From PowerShell in the project directory, replace `YOUR-USERNAME` with your GitHub username:

```powershell
git init
git add .
git commit -m "Build DB migration risk analyzer"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/DB-Migration-Risk-Analyzer.git
git push -u origin main
```

If Git asks for identity first, configure it with your own name and email using `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`. Do not commit access tokens or credentials.
