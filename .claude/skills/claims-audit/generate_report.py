#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Generate verification.md from inventory.json

Usage:
    python generate-report.py [--inventory PATH] [--output PATH]
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote


def load_inventory(path: Path) -> Dict[str, Any]:
    """Load and parse inventory JSON file."""
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def get_github_permalink(file_path: str, line: int | None, commit_ref: str = "Dev_new_gui") -> str:
    """Generate GitHub permalink for file:line reference."""
    if line is None:
        return f"../{file_path}"

    encoded_path = quote(file_path.replace("../", ""))
    return f"../{file_path}#L{line}"


def get_category(claim_id: str) -> str:
    """Infer category from claim ID."""
    if any(x in claim_id for x in ['docker', 'ansible', 'redis', 'postgresql', 'prometheus', 'chromadb']):
        return 'infrastructure'
    elif any(x in claim_id for x in ['api', 'rest', 'endpoint', 'websocket', 'a2a']):
        return 'api'
    elif any(x in claim_id for x in ['fastapi', 'uvicorn', 'celery', 'workers']):
        return 'architecture'
    else:
        return 'features'


def format_status_emoji(status: str) -> str:
    """Convert status to emoji."""
    status_map = {
        'wired': '✅',
        'partial': '⚠️',
        'broken': '❌'
    }
    return status_map.get(status, '❓')


def calculate_percentages(summary: Dict[str, int]) -> Dict[str, float]:
    """Calculate percentage for each status."""
    total = summary.get('total', 0)
    if total == 0:
        return {'wired': 0.0, 'partial': 0.0, 'broken': 0.0}

    return {
        'wired': (summary.get('wired', 0) / total) * 100,
        'partial': (summary.get('partial', 0) / total) * 100,
        'broken': (summary.get('broken', 0) / total) * 100
    }


def generate_summary_section(summary: Dict[str, int], percentages: Dict[str, float]) -> str:
    """Generate summary section with counts and percentages."""
    lines = [
        "## Summary\n",
        "| Status | Count | Percentage |",
        "|--------|-------|------------|",
        f"| ✅ wired | {summary.get('wired', 0)} | {percentages['wired']:.1f}% |",
        f"| ⚠️ partial | {summary.get('partial', 0)} | {percentages['partial']:.1f}% |",
        f"| ❌ broken | {summary.get('broken', 0)} | {percentages['broken']:.1f}% |",
        f"| **Total** | **{summary.get('total', 0)}** | **100.0%** |",
        ""
    ]
    return "\n".join(lines)


def format_evidence_list(evidence: List[Dict[str, Any]]) -> str:
    """Format evidence list with GitHub permalinks."""
    if not evidence:
        return "*(no evidence)*"

    items = []
    for e in evidence:
        kind = e.get('kind', 'unknown')
        file_path = e.get('file', '')
        line = e.get('line')
        url = e.get('url', '')

        if url:
            link = get_github_permalink(file_path, line)
            items.append(f"[{kind}]({link}) `{url}`")
        elif file_path:
            link = get_github_permalink(file_path, line)
            if line:
                items.append(f"[{kind}]({link})")
            else:
                items.append(f"[{kind}]({link})")
        else:
            items.append(f"*{kind}*")

    return ", ".join(items)


def generate_claim_entry(idx: int, claim: Dict[str, Any]) -> str:
    """Generate markdown entry for a single claim."""
    status = claim.get('status', 'unknown')
    status_emoji = format_status_emoji(status)

    capability = claim.get('capability', '*(unnamed)*')
    claim_text = claim.get('claim', '*(no claim text)*')

    source = claim.get('source', {})
    source_file = source.get('file', '')
    source_line = source.get('line')
    source_link = get_github_permalink(source_file, source_line) if source_file else '*(unknown)*'

    evidence = claim.get('evidence', [])
    evidence_str = format_evidence_list(evidence)

    notes = claim.get('notes', '')

    discovery_issue = claim.get('discovery_issue', '')
    if discovery_issue:
        notes += f" [Issue]({discovery_issue})"

    # Build row
    parts = [
        f"| {idx} ",
        f"| {capability} ",
        f'| "{claim_text}" ',
        f"| [{source_file}:{source_line}]({source_link}) " if source_file else "| *(unknown)* ",
        f"| {evidence_str} ",
        f"| {status_emoji} {status} ",
        f"| {notes} |"
    ]

    return "".join(parts)


def generate_category_section(category: str, claims: List[Dict[str, Any]], start_idx: int = 1) -> str:
    """Generate section for a category of claims."""
    category_title = category.replace('_', ' ').title()

    lines = [
        f"\n## {category_title}\n",
        "| # | Capability | Source Claim | Claim Location | Verified-by Artifact | Status | Notes |",
        "|---|-----------|-------------|----------------|---------------------|--------|-------|"
    ]

    for i, claim in enumerate(claims, start=start_idx):
        lines.append(generate_claim_entry(i, claim))

    lines.append("")
    return "\n".join(lines)


def group_claims_by_category(claims: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group claims by inferred category."""
    categories = {
        'infrastructure': [],
        'api': [],
        'features': [],
        'architecture': []
    }

    for claim in claims:
        claim_id = claim.get('id', '')
        category = get_category(claim_id)
        categories[category].append(claim)

    return categories


def generate_discovery_issues_section(claims: List[Dict[str, Any]]) -> str:
    """Generate discovery issues table."""
    broken_claims = [c for c in claims if c.get('status') == 'broken' and c.get('discovery_issue')]

    if not broken_claims:
        return ""

    lines = [
        "\n## Discovery Issues Filed\n",
        "| Finding | Issue |",
        "|---------|-------|"
    ]

    for claim in broken_claims:
        capability = claim.get('capability', '*(unnamed)*')
        issue_url = claim.get('discovery_issue', '')
        lines.append(f"| {capability} — {claim.get('notes', '').split('.')[0]} | [Link]({issue_url}) |")

    lines.append("")
    return "\n".join(lines)


def generate_report(inventory: Dict[str, Any]) -> str:
    """Generate complete verification.md report."""
    meta = inventory.get('meta', {})
    summary = inventory.get('summary', {})
    claims = inventory.get('claims', [])

    generated_at = meta.get('generated_at', datetime.now().strftime('%Y-%m-%d'))
    source_issue = meta.get('source_issue', '')

    percentages = calculate_percentages(summary)

    # Header
    lines = [
        "# AutoBot Capability Verification\n",
        f"> Auto-generated by `/claims-audit` skill. Run `claude /claims-audit` to refresh.",
        f"> Last verified: {generated_at}",
        f"> Source issue: [{source_issue}]({source_issue})\n" if source_issue else ""
    ]

    # Summary section
    lines.append(generate_summary_section(summary, percentages))

    # Group claims by category
    categorized = group_claims_by_category(claims)

    # Generate sections for each category
    idx = 1
    for category in ['infrastructure', 'api', 'features', 'architecture']:
        category_claims = categorized.get(category, [])
        if category_claims:
            lines.append(generate_category_section(category, category_claims, start_idx=idx))
            idx += len(category_claims)

    # Discovery issues
    lines.append(generate_discovery_issues_section(claims))

    # Footer
    lines.extend([
        "\n## How to Regenerate\n",
        "```bash",
        "claude /claims-audit",
        "```\n",
        "The `/claims-audit` skill at [`.claude/skills/claims-audit/SKILL.md`](../.claude/skills/claims-audit/SKILL.md):",
        "1. Walks `README.md`, `docs/` for capability claims",
        "2. For each claim, greps for endpoint declarations, test files, and Docker service definitions",
        "3. Writes `docs/verification.md` and `docs/verification-inventory.json` with current status",
        "4. Files `discovery:` issues for any `❌ broken` rows found"
    ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description='Generate verification.md from inventory.json')
    parser.add_argument(
        '--inventory',
        type=Path,
        default=Path('docs/verification-inventory.json'),
        help='Path to inventory JSON file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('docs/verification.md'),
        help='Path to output verification.md file'
    )

    args = parser.parse_args()

    # Load inventory
    inventory = load_inventory(args.inventory)

    # Generate report
    report = generate_report(inventory)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ Generated {args.output}")
    print(f"   {inventory['summary']['total']} claims verified")
    print(f"   ✅ {inventory['summary']['wired']} wired")
    print(f"   ⚠️  {inventory['summary']['partial']} partial")
    print(f"   ❌ {inventory['summary']['broken']} broken")


if __name__ == '__main__':
    main()
