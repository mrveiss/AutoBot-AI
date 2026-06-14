#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Verify claims from claims-audit extraction phase.

This script processes claims inventory JSON and verifies each claim
using appropriate verifiers (endpoint, test, config, code).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from verifiers import (
    BaseVerifier,
    CodeVerifier,
    ConfigVerifier,
    EndpointVerifier,
    TestVerifier,
)


class ClaimsVerifier:
    """Main verification orchestrator."""

    def __init__(self, repo_root: str):
        """Initialize verifier with repository root.

        Args:
            repo_root: Path to repository root directory
        """
        self.repo_root = repo_root
        self.verifiers: List[BaseVerifier] = [
            EndpointVerifier(repo_root),
            TestVerifier(repo_root),
            ConfigVerifier(repo_root),
            CodeVerifier(repo_root),
        ]

    def verify_claims(self, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify all claims and return results.

        Args:
            claims: List of claim dictionaries from extraction phase

        Returns:
            Dictionary with verification results and summary
        """
        verified_claims = []
        summary = {
            "total_claims": len(claims),
            "wired": 0,
            "partial": 0,
            "broken": 0,
            "manual": 0,
        }

        for claim in claims:
            # Determine which verifier to use
            verifier = self._select_verifier(claim)

            if verifier:
                # Verify the claim
                result = verifier.verify(claim)

                # Update claim with verification results
                claim["verification"] = {
                    "type": self._get_verifier_type(verifier),
                    **result.to_dict(),
                }

                # Update summary counts
                status = result.status.value
                summary[status] = summary.get(status, 0) + 1
            else:
                # No suitable verifier found
                claim["verification"] = {
                    "type": "manual",
                    "status": "manual",
                    "confidence": "low",
                    "notes": "No automated verifier available",
                    "last_verified": datetime.utcnow().isoformat(),
                }
                summary["manual"] += 1

            verified_claims.append(claim)

        return {
            "version": "1.0.0",
            "generated_at": datetime.utcnow().isoformat(),
            "summary": summary,
            "claims": verified_claims,
        }

    def _select_verifier(self, claim: Dict[str, Any]) -> BaseVerifier | None:
        """Select appropriate verifier for claim.

        Args:
            claim: Claim dictionary

        Returns:
            Verifier instance or None if no verifier can handle claim
        """
        # Try each verifier in order
        for verifier in self.verifiers:
            if verifier.can_verify(claim):
                return verifier
        return None

    def _get_verifier_type(self, verifier: BaseVerifier) -> str:
        """Get verification type name from verifier instance.

        Args:
            verifier: Verifier instance

        Returns:
            Type name (endpoint, test, config, code)
        """
        class_name = verifier.__class__.__name__
        return class_name.replace("Verifier", "").lower()


def load_claims(input_path: str) -> List[Dict[str, Any]]:
    """Load claims from JSON file.

    Args:
        input_path: Path to claims JSON file

    Returns:
        List of claim dictionaries
    """
    with open(input_path, "r") as f:
        data = json.load(f)

    # Handle both raw claims array and inventory format
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "claims" in data:
        return data["claims"]
    else:
        raise ValueError("Invalid claims JSON format")


def save_inventory(inventory: Dict[str, Any], output_path: str):
    """Save verification inventory to JSON file.

    Args:
        inventory: Verification inventory dictionary
        output_path: Path to output JSON file
    """
    with open(output_path, "w") as f:
        json.dump(inventory, f, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify documentation claims against codebase"
    )
    parser.add_argument(
        "input",
        help="Input claims JSON file (from extract-claims.py)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="docs/verification-inventory.json",
        help="Output inventory JSON file (default: docs/verification-inventory.json)",
    )
    parser.add_argument(
        "-r",
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verification progress",
    )

    args = parser.parse_args()

    # Resolve paths
    repo_root = Path(args.repo_root).resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output)

    if not repo_root.is_dir():
        print(f"Error: Repository root not found: {repo_root}", file=sys.stderr)
        return 1

    if not input_path.is_file():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Load claims
    if args.verbose:
        print(f"Loading claims from {input_path}...")

    try:
        claims = load_claims(str(input_path))
    except Exception as e:
        print(f"Error loading claims: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Loaded {len(claims)} claims")

    # Verify claims
    if args.verbose:
        print(f"Verifying claims...")

    verifier = ClaimsVerifier(str(repo_root))
    inventory = verifier.verify_claims(claims)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_inventory(inventory, str(output_path))

    # Print summary
    summary = inventory["summary"]
    print(f"\nVerification Summary:")
    print(f"  Total claims: {summary['total_claims']}")
    print(
        f"  ✅ Wired:     {summary['wired']} ({summary['wired']*100//summary['total_claims']}%)"
    )
    print(
        f"  ⚠️  Partial:   {summary['partial']} ({summary['partial']*100//summary['total_claims']}%)"
    )
    print(
        f"  ❌ Broken:    {summary['broken']} ({summary['broken']*100//summary['total_claims']}%)"
    )
    print(
        f"  📝 Manual:    {summary['manual']} ({summary['manual']*100//summary['total_claims']}%)"
    )
    print(f"\nInventory saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
