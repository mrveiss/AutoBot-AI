#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
File discovery issues for broken claims found during verification.

Usage:
    python file-issues.py [--inventory-path PATH] [--dry-run]

Options:
    --inventory-path PATH   Path to verification-inventory.json (default: docs/verification-inventory.json)
    --dry-run              Print what would be filed without actually creating issues
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def load_inventory(inventory_path: Path) -> Dict:
    """Load verification inventory from JSON file."""
    if not inventory_path.exists():
        raise FileNotFoundError(f"Inventory not found: {inventory_path}")

    with open(inventory_path, encoding='utf-8') as f:
        return json.load(f)


def save_inventory(inventory: Dict, inventory_path: Path) -> None:
    """Save updated inventory to JSON file."""
    with open(inventory_path, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)
        f.write('\n')  # trailing newline


def check_duplicate_issue(capability: str, claim: str) -> Optional[str]:
    """
    Check if an issue already exists for this claim.

    Returns the issue URL if found, None otherwise.
    """
    # Search GitHub for existing discovery issues matching this capability
    search_query = f"discovery {capability} in:title repo:mrveiss/AutoBot-AI"

    try:
        result = subprocess.run(
            ['gh', 'issue', 'list', '--repo', 'mrveiss/AutoBot-AI',
             '--search', search_query, '--json', 'url,title', '--limit', '5'],
            capture_output=True,
            text=True,
            check=True
        )

        issues = json.loads(result.stdout)

        # Look for exact match in title
        for issue in issues:
            if capability.lower() in issue['title'].lower():
                return issue['url']

        return None
    except (subprocess.CalledProcessError, Exception) as e:
        print(f"Warning: Failed to search for duplicates: {e}", file=sys.stderr)
        return None


def create_issue_body(claim_data: Dict) -> str:
    """Generate the issue body for a broken claim."""
    capability = claim_data['capability']
    claim_text = claim_data['claim']
    source = claim_data['source']
    notes = claim_data.get('notes', 'No additional notes.')
    evidence = claim_data.get('evidence', [])

    # Build evidence section
    evidence_lines = []
    if evidence:
        evidence_lines.append("**Evidence found:**")
        for ev in evidence:
            kind = ev.get('kind', 'unknown')
            file_path = ev.get('file', 'unknown')
            line = ev.get('line')
            if line:
                evidence_lines.append(f"- {kind}: `{file_path}:{line}`")
            else:
                evidence_lines.append(f"- {kind}: `{file_path}`")
    else:
        evidence_lines.append("**No evidence found** — capability not wired")

    # Build issue body
    body = f"""## Finding

**Capability:** {capability}
**Claim source:** [{source['file']}:{source['line']}](../{source['file']}#L{source['line']})
**Status:** ❌ broken

## Evidence

{chr(10).join(evidence_lines)}

## Details

{notes}

## Impact

Users following the documentation will expect this capability to work, but it is currently broken or unreachable. This creates a gap between documented and actual functionality.

## Suggested Fix

1. Verify the evidence and notes above to understand the root cause
2. Either:
   - Wire the capability properly (add missing endpoint/service/registration), OR
   - Remove the claim from documentation if the capability is not intended to be available
3. Update verification inventory to reflect the fix
4. Re-run `/claims-audit` to verify status is now ✅ wired

## Related

- Verification report: [docs/verification.md](../docs/verification.md)
- Verification inventory: [docs/verification-inventory.json](../docs/verification-inventory.json)
- Parent issue: https://github.com/mrveiss/AutoBot-AI/issues/7359

*Filed by `/claims-audit` on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*
"""

    return body


def file_issue(claim_data: Dict, dry_run: bool = False) -> Optional[str]:
    """
    File a discovery issue for a broken claim.

    Returns the issue URL if created, None if skipped or failed.
    """
    capability = claim_data['capability']
    claim_text = claim_data['claim']

    # Check for duplicates first
    existing_url = check_duplicate_issue(capability, claim_text)
    if existing_url:
        print(f"  ⏭️  Skipped (duplicate found): {existing_url}")
        return existing_url

    # Generate issue title
    # Format: "discovery(docs): <claim text> not verified"
    title_claim = claim_text[:80] + '...' if len(claim_text) > 80 else claim_text
    title = f"discovery(docs): {title_claim} not verified"

    # Generate issue body
    body = create_issue_body(claim_data)

    if dry_run:
        print(f"  [DRY RUN] Would file issue:")
        print(f"    Title: {title}")
        print(f"    Labels: tech-debt, docs")
        print(f"    Body preview: {body[:200]}...")
        return None

    # File the issue using gh CLI
    try:
        result = subprocess.run(
            ['gh', 'issue', 'create',
             '--repo', 'mrveiss/AutoBot-AI',
             '--title', title,
             '--label', 'tech-debt,docs',
             '--body', body],
            capture_output=True,
            text=True,
            check=True
        )

        issue_url = result.stdout.strip()
        print(f"  ✅ Filed: {issue_url}")
        return issue_url

    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to file issue: {e.stderr}", file=sys.stderr)
        return None


def process_broken_claims(inventory: Dict, dry_run: bool = False) -> List[Dict]:
    """
    Process all broken claims and file issues for them.

    Returns a list of filed issues with metadata.
    """
    claims = inventory.get('claims', [])
    filed_issues = []

    for claim in claims:
        if claim.get('status') != 'broken':
            continue

        # Skip if already has a discovery issue
        if claim.get('discovery_issue'):
            print(f"  ⏭️  Skipped (already filed): {claim['capability']}")
            continue

        print(f"📝 Processing: {claim['capability']}")

        issue_url = file_issue(claim, dry_run=dry_run)

        if issue_url:
            # Update the claim with the discovery issue URL
            claim['discovery_issue'] = issue_url
            filed_issues.append({
                'capability': claim['capability'],
                'url': issue_url
            })

    return filed_issues


def main():
    parser = argparse.ArgumentParser(
        description='File discovery issues for broken claims',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--inventory-path',
        type=Path,
        default=Path('docs/verification-inventory.json'),
        help='Path to verification inventory JSON file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be filed without creating issues'
    )

    args = parser.parse_args()

    # Load inventory
    print(f"📂 Loading inventory from {args.inventory_path}")
    try:
        inventory = load_inventory(args.inventory_path)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

    # Process broken claims
    print(f"\n🔍 Processing broken claims...")
    filed_issues = process_broken_claims(inventory, dry_run=args.dry_run)

    # Save updated inventory (unless dry run)
    if not args.dry_run and filed_issues:
        print(f"\n💾 Updating inventory...")
        save_inventory(inventory, args.inventory_path)
        print(f"  ✅ Saved to {args.inventory_path}")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Total broken claims: {len([c for c in inventory['claims'] if c.get('status') == 'broken'])}")
    print(f"  Issues filed this run: {len(filed_issues)}")

    if filed_issues:
        print(f"\nFiled issues:")
        for issue in filed_issues:
            print(f"  - {issue['capability']}")
            print(f"    → {issue['url']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
