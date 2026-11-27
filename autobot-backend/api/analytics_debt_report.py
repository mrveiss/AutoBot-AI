# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Markdown rendering of a technical-debt report (split from analytics_debt.py, #398)."""

def _build_debt_executive_summary(debt_data: dict) -> str:
    """Build executive summary section of report (Issue #398: extracted)."""
    summary = debt_data.get("summary", {})
    return f"""# Technical Debt Report

**Generated:** {debt_data.get('timestamp', 'N/A')}

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Debt Items | {summary.get('total_items', 0)} |
| Estimated Hours | {summary.get('total_hours', 0):.1f} |
| Estimated Cost | ${summary.get('total_cost_usd', 0):,.2f} |
| Hourly Rate Used | ${summary.get('hourly_rate', 75)}/hr |
"""


def _build_debt_tables(debt_data: dict) -> str:
    """Build severity, category, files, and ROI tables (Issue #398: extracted)."""
    summary = debt_data.get("summary", {})

    # Severity section
    severity_rows = [f"| {sev.capitalize()} | {count} |" for sev, count in summary.get("by_severity", {}).items()]
    result = "\n## Debt by Severity\n\n| Severity | Count |\n|----------|-------|\n" + "\n".join(severity_rows) + "\n"

    # Category section
    category_rows = [
        f"| {cat.replace('_', ' ').title()} | {count} |" for cat, count in summary.get("by_category", {}).items()
    ]
    result += "\n## Debt by Category\n\n| Category | Count |\n|----------|-------|\n" + "\n".join(category_rows) + "\n"

    # Top files section
    file_rows = [
        f"| {f.get('file', 'unknown')[-50:]} | {f.get('hours', 0):.1f} | ${f.get('cost_usd', 0):.2f} |"
        for f in debt_data.get("top_files", [])[:10]
    ]
    result += (
        "\n## Top Files by Debt\n\n| File | Hours | Cost |\n|------|-------|------|\n" + "\n".join(file_rows) + "\n"
    )

    # ROI priorities section
    roi_rows = []
    for item in debt_data.get("roi_ranking", [])[:10]:
        desc = item.get("description", "")[:40]
        roi = item.get("roi_score", 0)
        hours = item.get("estimated_hours", 0)
        complexity = item.get("fix_complexity", "unknown")
        roi_rows.append(f"| {desc}... | {roi} | {hours:.1f} | {complexity} |")
    result += (
        "\n## Top ROI Priorities (Quick Wins)\n\n"
        "| Description | ROI | Hours | Complexity |\n"
        "|-------------|-----|-------|------------|\n" + "\n".join(roi_rows) + "\n"
    )

    return result


def _build_debt_recommendations() -> str:
    """Build recommendations section (Issue #398: extracted)."""
    return """
## Recommendations

1. **Start with Quick Wins**: Address items with high ROI scores first
2. **Focus on Critical Issues**: Prioritize critical severity items
3. **Track Progress**: Run debt calculation regularly to monitor trends
4. **Set Targets**: Aim to reduce total debt hours by 10% per sprint
"""


def generate_markdown_report(debt_data: dict) -> str:
    """Generate complete markdown debt report (Issue #398: extracted)."""
    return _build_debt_executive_summary(debt_data) + _build_debt_tables(debt_data) + _build_debt_recommendations()
