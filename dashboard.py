"""Streamlit dashboard for static SQL migration risk analysis."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyzer import AnalysisReport, MigrationAnalyzer
from reporter import format_json, format_text


ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "test_files"
SAMPLE_FILES = {
    "safe_migration.sql": SAMPLE_DIR / "safe_migration.sql",
    "risky_migration.sql": SAMPLE_DIR / "risky_migration.sql",
    "mixed_migration.sql": SAMPLE_DIR / "mixed_migration.sql",
}
SEVERITIES = ("HIGH", "MEDIUM", "LOW")
COLORS = {"HIGH": "#f05d6c", "MEDIUM": "#f4a340", "LOW": "#40c99a"}
TABLE_COLUMNS = [
    "File Name",
    "Line Number",
    "Risk Level",
    "Rule Name",
    "Risk Score",
    "SQL Statement",
    "Explanation",
]


def _empty_report() -> AnalysisReport:
    return AnalysisReport(files_analyzed=[], issues=[], errors=[])


def aggregate_reports(reports: dict[str, AnalysisReport]) -> AnalysisReport:
    """Combine source reports without mutating the session's stored reports."""
    files: list[str] = []
    issues = []
    errors: list[str] = []
    for report in reports.values():
        files.extend(report.files_analyzed)
        issues.extend(report.issues)
        errors.extend(report.errors)
    return AnalysisReport(
        files_analyzed=list(dict.fromkeys(files)),
        issues=issues,
        errors=errors,
    )


def build_findings_dataframe(report: AnalysisReport) -> pd.DataFrame:
    """Create the shared table model used by the dashboard and CSV export."""
    rows = [
        {
            "File Name": Path(issue.file).name,
            "Line Number": issue.line,
            "Risk Level": issue.risk_level,
            "Rule Name": issue.rule,
            "Risk Score": issue.risk_score,
            "SQL Statement": issue.statement,
            "Explanation": issue.explanation,
        }
        for issue in report.issues
    ]
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def build_csv_report(report: AnalysisReport) -> str:
    """Return a CSV with a summary record followed by individual finding rows."""
    summary = report.summary()
    columns = [
        "Record Type",
        "Files Analyzed",
        "Total Findings",
        "High Findings",
        "Medium Findings",
        "Low Findings",
        "Overall Risk Score",
        "Overall Risk",
        *TABLE_COLUMNS,
    ]
    rows: list[dict[str, Any]] = [
        {
            "Record Type": "SUMMARY",
            "Files Analyzed": len(report.files_analyzed),
            "Total Findings": summary["total_issues"],
            "High Findings": summary["high"],
            "Medium Findings": summary["medium"],
            "Low Findings": summary["low"],
            "Overall Risk Score": summary["total_score"],
            "Overall Risk": summary["overall_risk"],
            "File Name": "; ".join(Path(name).name for name in report.files_analyzed),
        }
    ]
    rows.extend(
        {"Record Type": "FINDING", **row}
        for row in build_findings_dataframe(report).to_dict(orient="records")
    )
    normalized_rows = [
        {column: row.get(column, "") for column in columns}
        for row in rows
    ]
    return pd.DataFrame(normalized_rows, columns=columns).to_csv(index=False)


def _source_report(path: Path, display_name: str) -> AnalysisReport:
    report = MigrationAnalyzer().analyze([path])
    return AnalysisReport(
        files_analyzed=[display_name for _ in report.files_analyzed],
        issues=[replace(issue, file=display_name) for issue in report.issues],
        errors=report.errors,
    )


def _analyze_selection(
    uploads: list[Any],
    selected_samples: list[str],
    max_size_mb: int,
) -> tuple[list[str], list[str]]:
    """Analyze the selected sources and update results by source key."""
    stored: dict[str, AnalysisReport] = st.session_state.analysis_batches
    messages: list[str] = []
    errors: list[str] = []
    planned: list[tuple[str, str, bytes | Path]] = []

    for uploaded in uploads:
        content = uploaded.getvalue()
        key = f"upload:{uploaded.name}"
        if Path(uploaded.name).suffix.lower() != ".sql":
            errors.append(f"{uploaded.name}: only .sql files can be analyzed.")
        elif not content.strip():
            errors.append(f"{uploaded.name}: the SQL file is empty.")
        elif len(content) > max_size_mb * 1024 * 1024:
            errors.append(f"{uploaded.name}: exceeds the {max_size_mb} MB upload limit.")
        else:
            planned.append((key, uploaded.name, content))

    for sample_name in selected_samples:
        sample_path = SAMPLE_FILES[sample_name]
        if not sample_path.is_file():
            errors.append(f"Sample file is missing: {sample_path}")
        else:
            planned.append((f"sample:{sample_name}", sample_name, sample_path))

    if not planned and not errors:
        errors.append("Choose at least one uploaded SQL file or sample migration to analyze.")

    progress = st.progress(0, text="Preparing static analysis...")
    analyzer_errors: list[str] = []
    for index, (key, display_name, source) in enumerate(planned, start=1):
        progress.progress(
            index / len(planned),
            text=f"Analyzing {display_name} ({index}/{len(planned)})",
        )
        try:
            if isinstance(source, bytes):
                with tempfile.TemporaryDirectory(prefix="migration-risk-") as directory:
                    temp_path = Path(directory) / f"migration-{index:04d}.sql"
                    temp_path.write_bytes(source)
                    result = _source_report(temp_path, display_name)
            else:
                result = _source_report(source, display_name)
            stored[key] = result
            if result.errors:
                analyzer_errors.extend(f"{display_name}: {error}" for error in result.errors)
            else:
                messages.append(display_name)
        except Exception as error:
            analyzer_errors.append(f"{display_name}: analysis failed ({error})")
            stored[key] = AnalysisReport(
                files_analyzed=[],
                issues=[],
                errors=[f"{display_name}: analysis failed ({error})"],
            )
    progress.empty()
    return messages, [*errors, *analyzer_errors]


def _metric_card(label: str, value: str | int, tone: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="metric-card metric-{tone}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _base_layout() -> None:
    st.set_page_config(
        page_title="DB Migration Risk Analyzer",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background: #0b1020; color: #e6eaf2; }
        [data-testid="stHeader"] { background: rgba(11, 16, 32, .94); }
        [data-testid="stSidebar"] {
            background: #10172a;
            border-right: 1px solid #222c43;
        }
        .block-container { max-width: 1480px; padding-top: 1.7rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: #f3f5fb; letter-spacing: -.025em; }
        p, label, .stCaption { color: #aab4c8; }
        .dashboard-header {
            display: flex; align-items: flex-start; justify-content: space-between;
            gap: 1rem; padding: 1.5rem 1.6rem; margin-bottom: 1.35rem;
            border: 1px solid #27324a; border-radius: 18px;
            background: linear-gradient(120deg, #151d34 0%, #11182b 60%, #171a36 100%);
        }
        .dashboard-title { margin: 0; color: #f4f6fc; font-size: 1.65rem; font-weight: 750; }
        .dashboard-subtitle { margin: .45rem 0 0; color: #aab4c8; font-size: .96rem; }
        .engine-badge {
            white-space: nowrap; border: 1px solid #574fba; color: #c5c0ff;
            background: #27254a; border-radius: 999px; padding: .48rem .78rem;
            font-size: .68rem; font-weight: 750; letter-spacing: .09em;
        }
        .metric-card {
            min-height: 106px; padding: 1rem 1.05rem; margin-bottom: .75rem;
            border: 1px solid #26314a; border-radius: 15px;
            background: linear-gradient(145deg, #151e33, #111827);
        }
        .metric-label { color: #9eabc1; font-size: .78rem; font-weight: 600; }
        .metric-value { margin-top: .55rem; color: #f2f5fc; font-size: 1.75rem; font-weight: 750; }
        .metric-high { border-color: #633141; }
        .metric-high .metric-value { color: #ff7583; }
        .metric-medium { border-color: #614923; }
        .metric-medium .metric-value { color: #ffba62; }
        .metric-low { border-color: #245448; }
        .metric-low .metric-value { color: #5cdbad; }
        .metric-accent { border-color: #424084; }
        .metric-accent .metric-value { color: #a9a2ff; }
        .section-kicker {
            color: #8d9bb4; font-size: .75rem; font-weight: 750;
            letter-spacing: .12em; text-transform: uppercase; margin: .5rem 0 .4rem;
        }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {
            border: 1px solid #242e44; border-radius: 14px; overflow: hidden;
            background: #111827;
        }
        div.stButton > button {
            border-radius: 9px; border: 1px solid #5149a7;
            background: #554cc5; color: white; font-weight: 650;
        }
        div.stButton > button:hover { border-color: #8e87f5; background: #655ce0; color: white; }
        a { color: #a9a2ff !important; }
        hr { border-color: #273149; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _sidebar() -> tuple[str, list[Any], list[str], list[str], int, bool]:
    st.sidebar.markdown("## DB Migration Risk Analyzer")
    page = st.sidebar.radio(
        "Dashboard navigation",
        ("Overview", "Migration Analysis", "Risk Findings", "Reports", "About"),
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    st.sidebar.markdown("### Migration inputs")
    uploads = st.sidebar.file_uploader(
        "Upload SQL migration files",
        type=["sql"],
        accept_multiple_files=True,
        help="SQL is inspected as text only; uploaded files are never executed.",
        key="migration_uploads",
    ) or []
    selected_samples = st.sidebar.multiselect(
        "Browse sample SQL files",
        options=list(SAMPLE_FILES),
        help="Sample files are read from the existing test_files folder.",
    )
    max_size_mb = st.sidebar.slider(
        "Maximum upload size per file (MB)",
        min_value=1,
        max_value=25,
        value=10,
        help="Files larger than this limit are skipped.",
    )
    if st.sidebar.button("Analyze selected files", type="primary", use_container_width=True):
        messages, errors = _analyze_selection(uploads, selected_samples, max_size_mb)
        if messages:
            st.session_state.last_analysis_message = (
                f"Analysis complete: {len(messages)} file(s) analyzed."
            )
        if errors:
            st.session_state.last_analysis_errors = errors
        else:
            st.session_state.last_analysis_errors = []

    severity_filter = st.sidebar.multiselect(
        "Filter risk severity",
        options=list(SEVERITIES),
        default=list(SEVERITIES),
        key="severity_filter",
    )
    with st.sidebar.expander("About this project"):
        st.caption(
            "A static SQL review aid for migration changes. It does not connect to or "
            "execute statements against a database."
        )
    if st.sidebar.button("Clear analyzed results", use_container_width=True):
        st.session_state.analysis_batches = {}
        st.session_state.last_analysis_message = ""
        st.session_state.last_analysis_errors = []
        st.rerun()
    return page, uploads, selected_samples, severity_filter, max_size_mb, False


def _render_header() -> None:
    st.markdown(
        """
        <div class="dashboard-header">
            <div>
                <h1 class="dashboard-title">DB MIGRATION RISK ANALYZER</h1>
                <p class="dashboard-subtitle">
                    Intelligent SQL Migration Risk Detection &amp; Developer Safety Analysis
                </p>
            </div>
            <div class="engine-badge">STATIC SQL ANALYSIS ENGINE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(report: AnalysisReport) -> None:
    st.title("Overview")
    st.caption("A live summary of the migration files analyzed in this session.")
    summary = report.summary()
    metric_rows = (
        (
            ("Total Files Analyzed", len(report.files_analyzed), "accent"),
            ("Total Findings", summary["total_issues"], "neutral"),
            ("HIGH Risk Findings", summary["high"], "high"),
        ),
        (
            ("MEDIUM Risk Findings", summary["medium"], "medium"),
            ("LOW Risk Findings", summary["low"], "low"),
            ("Overall Risk Score", summary["total_score"], "accent"),
        ),
    )
    for row in metric_rows:
        columns = st.columns(3)
        for column, (label, value, tone) in zip(columns, row):
            with column:
                _metric_card(label, value, tone)
    st.caption(f"Overall classification: **{summary['overall_risk']}**")

    counts = {level: int(summary[level.lower()]) for level in SEVERITIES}
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-kicker">Risk mix</div>', unsafe_allow_html=True)
        fig = go.Figure(
            go.Pie(
                labels=list(counts),
                values=list(counts.values()),
                hole=0.68,
                marker={"colors": [COLORS[level] for level in counts]},
                textinfo="label+value",
                hovertemplate="%{label}: %{value} finding(s)<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            margin={"l": 12, "r": 12, "t": 24, "b": 12},
            height=330,
            showlegend=True,
            legend={"orientation": "h", "y": -0.08},
        )
        st.plotly_chart(fig, use_container_width=True, key="risk_donut")
    with right:
        st.markdown(
            '<div class="section-kicker">Severity distribution</div>', unsafe_allow_html=True
        )
        fig = go.Figure(
            go.Bar(
                x=list(counts),
                y=list(counts.values()),
                marker_color=[COLORS[level] for level in counts],
                hovertemplate="%{x}: %{y} finding(s)<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            margin={"l": 12, "r": 12, "t": 24, "b": 12},
            height=330,
            yaxis_title="Findings",
            xaxis_title="Severity",
        )
        st.plotly_chart(fig, use_container_width=True, key="severity_bar")

    findings = build_findings_dataframe(report)
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-kicker">Findings by SQL file</div>', unsafe_allow_html=True)
        if findings.empty:
            st.info("Analyze SQL files to populate the charts.")
        else:
            file_counts = findings["File Name"].value_counts().sort_values(ascending=True)
            fig = go.Figure(
                go.Bar(
                    x=file_counts.values,
                    y=file_counts.index,
                    orientation="h",
                    marker_color="#7770df",
                    hovertemplate="%{y}: %{x} finding(s)<extra></extra>",
                )
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#111827",
                plot_bgcolor="#111827",
                margin={"l": 12, "r": 12, "t": 24, "b": 12},
                height=330,
                xaxis_title="Findings",
            )
            st.plotly_chart(fig, use_container_width=True, key="file_findings")
    with right:
        st.markdown(
            '<div class="section-kicker">Findings by detection rule</div>',
            unsafe_allow_html=True,
        )
        if findings.empty:
            st.info("Rule counts appear after a migration is analyzed.")
        else:
            rule_counts = findings["Rule Name"].value_counts().sort_values(ascending=True)
            fig = go.Figure(
                go.Bar(
                    x=rule_counts.values,
                    y=rule_counts.index,
                    orientation="h",
                    marker_color="#568ee8",
                    hovertemplate="%{y}: %{x} finding(s)<extra></extra>",
                )
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#111827",
                plot_bgcolor="#111827",
                margin={"l": 12, "r": 12, "t": 24, "b": 12},
                height=330,
                xaxis_title="Findings",
            )
            st.plotly_chart(fig, use_container_width=True, key="rule_findings")


def _filtered_findings(report: AnalysisReport, selected_levels: list[str]) -> pd.DataFrame:
    findings = build_findings_dataframe(report)
    if findings.empty:
        return findings
    if not selected_levels:
        return findings.iloc[0:0]
    return findings[findings["Risk Level"].isin(selected_levels)].copy()


def _styled_findings(findings: pd.DataFrame) -> Any:
    def color_risk(value: str) -> str:
        colors = {
            "HIGH": "background-color: #4a202d; color: #ff8a96; font-weight: 700",
            "MEDIUM": "background-color: #49351d; color: #ffc16f; font-weight: 700",
            "LOW": "background-color: #193d35; color: #68ddb1; font-weight: 700",
        }
        return colors.get(value, "")

    return findings.style.map(color_risk, subset=["Risk Level"])


def _render_findings(report: AnalysisReport, selected_levels: list[str]) -> None:
    st.title("Risk Findings")
    st.caption("Search, filter, and sort individual static-analysis findings.")
    findings = _filtered_findings(report, selected_levels)
    search = st.text_input("Search filename or SQL statement", placeholder="e.g. users or DROP TABLE")
    rules = sorted(findings["Rule Name"].unique().tolist()) if not findings.empty else []
    selected_rules = st.multiselect("Filter detection rules", options=rules, default=rules)
    sort_column = st.selectbox("Sort by", options=TABLE_COLUMNS, index=2)
    descending = st.toggle("Descending", value=False)

    if search:
        query = search.casefold()
        mask = findings["File Name"].str.casefold().str.contains(query, na=False) | findings[
            "SQL Statement"
        ].str.casefold().str.contains(query, na=False)
        findings = findings[mask]
    if selected_rules:
        findings = findings[findings["Rule Name"].isin(selected_rules)]
    elif rules:
        findings = findings.iloc[0:0]
    if not findings.empty:
        findings = findings.sort_values(sort_column, ascending=not descending, kind="stable")
        st.dataframe(
            _styled_findings(findings),
            use_container_width=True,
            hide_index=True,
            height=min(600, max(180, 42 * (len(findings) + 1))),
        )
    else:
        st.info("No findings match the selected filters. Analyze a sample or upload a migration.")


def _render_analysis(
    report: AnalysisReport,
    uploads: list[Any],
    selected_samples: list[str],
    severity_filter: list[str],
    max_size_mb: int,
) -> None:
    st.title("Migration Analysis")
    st.caption("Upload SQL or select an included sample. Analysis is static; SQL is never executed.")
    if st.session_state.last_analysis_message:
        st.success(st.session_state.last_analysis_message)
    for error in st.session_state.last_analysis_errors:
        st.error(error)

    st.markdown("#### Selected files")
    selected_rows = [
        {
            "Source": uploaded.name,
            "Type": "Upload",
            "Size": f"{len(uploaded.getvalue()) / 1024:.1f} KB",
        }
        for uploaded in uploads
    ]
    for sample_name in selected_samples:
        sample_path = SAMPLE_FILES[sample_name]
        size = f"{sample_path.stat().st_size / 1024:.1f} KB" if sample_path.is_file() else "Missing"
        selected_rows.append({"Source": sample_name, "Type": "Sample", "Size": size})
    if selected_rows:
        st.dataframe(pd.DataFrame(selected_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Choose SQL files in the sidebar, or select a sample migration.")

    st.caption(f"Maximum upload size: {max_size_mb} MB per file.")
    if st.button("Analyze selected files", type="primary", key="analyze_page"):
        messages, errors = _analyze_selection(uploads, selected_samples, max_size_mb)
        st.session_state.last_analysis_message = (
            f"Analysis complete: {len(messages)} file(s) analyzed." if messages else ""
        )
        st.session_state.last_analysis_errors = errors
        st.rerun()

    st.divider()
    st.markdown("#### Current session findings")
    findings = _filtered_findings(report, severity_filter)
    if findings.empty:
        st.info("No findings to show. Start an analysis from the sidebar or above.")
    else:
        st.dataframe(_styled_findings(findings), use_container_width=True, hide_index=True)


def _render_reports(report: AnalysisReport) -> None:
    st.title("Reports")
    st.caption("Download the current session's combined analysis report.")
    if not report.files_analyzed and not report.errors:
        st.info("Run an analysis to generate downloadable reports.")
        return
    summary = report.summary()
    st.write(
        f"**{len(report.files_analyzed)}** file(s) · "
        f"**{summary['total_issues']}** finding(s) · "
        f"Overall risk **{summary['overall_risk']}** · "
        f"Score **{summary['total_score']}**"
    )
    json_data = format_json(report)
    csv_data = build_csv_report(report)
    text_data = format_text(report)
    columns = st.columns(3)
    columns[0].download_button(
        "Download JSON",
        data=json_data,
        file_name="db_migration_risk_report.json",
        mime="application/json",
        use_container_width=True,
    )
    columns[1].download_button(
        "Download CSV",
        data=csv_data,
        file_name="db_migration_risk_report.csv",
        mime="text/csv",
        use_container_width=True,
    )
    columns[2].download_button(
        "Download TXT",
        data=text_data,
        file_name="db_migration_risk_report.txt",
        mime="text/plain",
        use_container_width=True,
    )
    with st.expander("Preview JSON report"):
        st.code(json.dumps(json.loads(json_data), indent=2), language="json")


def _render_about() -> None:
    st.title("About")
    st.markdown(
        """
        This project is a Python developer tool for reviewing SQL migrations before
        deployment. It reuses the repository's existing analyzer and supports both a
        command-line workflow and this interactive dashboard.

        **How it works:** migration text is read from disk (or a temporary file for an
        upload), passed to the existing static analyzer, and summarized as line-numbered
        findings. Uploaded SQL is not run against a database.

        **Scoring:** LOW = 1, MEDIUM = 5, HIGH = 10. Finding scores are added; the
        existing analyzer classifies totals of 0 as NONE, 1–4 as LOW, 5–9 as MEDIUM,
        and 10+ as HIGH.

        **Limitations:** the engine uses regex-based static analysis rather than a full
        dialect-aware SQL parser. A finding is a review signal; no findings do not
        guarantee that a migration is safe.
        """
    )
    st.markdown("#### Screenshots")
    st.caption("Add portfolio screenshots here after capturing the Overview and Findings pages.")
    st.code(
        "docs/screenshots/dashboard-overview.png\n"
        "docs/screenshots/dashboard-findings.png",
        language="text",
    )


def main() -> None:
    _base_layout()
    if "analysis_batches" not in st.session_state:
        st.session_state.analysis_batches = {}
    if "last_analysis_message" not in st.session_state:
        st.session_state.last_analysis_message = ""
    if "last_analysis_errors" not in st.session_state:
        st.session_state.last_analysis_errors = []

    page, uploads, selected_samples, severity_filter, max_size_mb, _ = _sidebar()
    _render_header()
    report = aggregate_reports(st.session_state.analysis_batches)

    if page == "Overview":
        _render_overview(report)
    elif page == "Migration Analysis":
        _render_analysis(report, uploads, selected_samples, severity_filter, max_size_mb)
    elif page == "Risk Findings":
        _render_findings(report, severity_filter)
    elif page == "Reports":
        _render_reports(report)
    else:
        _render_about()


if __name__ == "__main__":
    main()
