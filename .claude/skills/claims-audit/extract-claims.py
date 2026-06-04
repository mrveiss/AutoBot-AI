#!/usr/bin/env python3
"""
Extract claims from documentation for verification.

Parses README.md, docs/, and CLAUDE.md to identify:
- Infrastructure claims (services, databases, ports)
- Feature claims (capabilities, integrations, support)
- API claims (endpoints, methods, authentication)
- Architecture claims (components, patterns, deployment)

Output: JSON with source file:line citations.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


class ClaimExtractor:
    """Extract claims from documentation using pattern matching."""

    def __init__(self, patterns_dir: Path, repo_root: Path = None):
        self.patterns_dir = patterns_dir
        self.repo_root = repo_root
        self.patterns = self._load_patterns()
        self.claims = []

    def _load_patterns(self) -> Dict[str, Any]:
        """Load all pattern files from patterns directory."""
        patterns = {}
        for pattern_file in self.patterns_dir.glob("*.json"):
            category = pattern_file.stem
            with open(pattern_file, "r", encoding="utf-8") as f:
                patterns[category] = json.load(f)
        return patterns

    def _relativize(self, file_path: Path) -> str:
        """Return path relative to repo_root if known, otherwise basename only."""
        if self.repo_root:
            try:
                return str(file_path.relative_to(self.repo_root))
            except ValueError:
                pass
        return file_path.name

    def extract_from_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extract claims from a single file."""
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

        file_claims = []
        in_code_block = False

        for line_num, line in enumerate(lines, start=1):
            # Track code blocks
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            # Skip code blocks, empty lines, and pure markdown headers
            if in_code_block or not line.strip():
                continue

            # Skip lines that are just URLs or badges
            if self._is_url_line(line) or self._is_badge_line(line):
                continue

            # Skip lines with only markdown formatting
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) < 100:
                # Headers are usually metadata, skip short ones
                continue

            for category, pattern_data in self.patterns.items():
                for pattern_def in pattern_data.get("patterns", []):
                    pattern = pattern_def["pattern"]
                    matches = list(re.finditer(pattern, line, re.IGNORECASE))
                    for match in matches:
                        # Skip matches that are inside URLs
                        if self._is_in_url(line, match.start()):
                            continue

                        # Skip very short matches that might be noise
                        if len(match.group(0).strip()) < 2:
                            continue

                        claim = {
                            "category": category,
                            "type": pattern_def["type"],
                            "claim": line.strip(),
                            "matched_text": match.group(0),
                            "source": {
                                "file": self._relativize(file_path),
                                "line": line_num,
                            },
                            "pattern_description": pattern_def["description"],
                        }
                        file_claims.append(claim)

        return file_claims

    def _is_url_line(self, line: str) -> bool:
        """Check if line is primarily a URL."""
        stripped = line.strip()
        return bool(re.match(r"^\[.*\]\(https?://.*\)$", stripped)) or bool(
            re.match(r"^https?://.*$", stripped)
        )

    def _is_badge_line(self, line: str) -> bool:
        """Check if line is a badge."""
        return "![" in line and "badge.svg" in line

    def _is_in_url(self, line: str, position: int) -> bool:
        """Check if a match position is inside a URL."""
        # Find all URLs in the line
        url_pattern = r"https?://[^\s\)]+"
        for url_match in re.finditer(url_pattern, line):
            if url_match.start() <= position < url_match.end():
                return True
        return False

    def extract_from_directory(
        self, dir_path: Path, glob_pattern: str = "**/*.md"
    ) -> List[Dict[str, Any]]:
        """Extract claims from all matching files in a directory."""
        dir_claims = []
        for file_path in dir_path.glob(glob_pattern):
            if file_path.is_file():
                file_claims = self.extract_from_file(file_path)
                dir_claims.extend(file_claims)
        return dir_claims

    def extract_all(self, repo_root: Path) -> List[Dict[str, Any]]:
        """Extract claims from all documentation sources."""
        all_claims = []

        # README.md
        readme = repo_root / "README.md"
        if readme.exists():
            all_claims.extend(self.extract_from_file(readme))

        # docs/
        docs_dir = repo_root / "docs"
        if docs_dir.exists():
            all_claims.extend(self.extract_from_directory(docs_dir))

        # CLAUDE.md
        claude_md = repo_root / "CLAUDE.md"
        if claude_md.exists():
            all_claims.extend(self.extract_from_file(claude_md))

        return all_claims

    def deduplicate_claims(self, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate claims (same claim text from same file)."""
        seen = set()
        unique_claims = []
        for claim in claims:
            key = (claim["claim"], claim["source"]["file"])
            if key not in seen:
                seen.add(key)
                unique_claims.append(claim)
        return unique_claims

    def save_claims(self, claims: List[Dict[str, Any]], output_path: Path):
        """Save extracted claims to JSON file."""
        output_data = {
            "total_claims": len(claims),
            "by_category": self._count_by_category(claims),
            "by_type": self._count_by_type(claims),
            "claims": claims,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def _count_by_category(self, claims: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count claims by category."""
        counts = {}
        for claim in claims:
            category = claim["category"]
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _count_by_type(self, claims: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count claims by type."""
        counts = {}
        for claim in claims:
            claim_type = f"{claim['category']}.{claim['type']}"
            counts[claim_type] = counts.get(claim_type, 0) + 1
        return counts


def main():
    """Main entry point."""
    # Determine paths
    script_dir = Path(__file__).parent
    patterns_dir = script_dir / "patterns"
    repo_root = (
        script_dir.parent.parent.parent
    )  # .claude/skills/claims-audit -> repo root

    if not patterns_dir.exists():
        print(f"Error: Patterns directory not found: {patterns_dir}", file=sys.stderr)
        sys.exit(1)

    # Extract claims
    extractor = ClaimExtractor(patterns_dir, repo_root)
    print(f"Extracting claims from {repo_root}...")
    claims = extractor.extract_all(repo_root)
    print(f"Found {len(claims)} total claims")

    # Deduplicate
    unique_claims = extractor.deduplicate_claims(claims)
    print(f"After deduplication: {len(unique_claims)} unique claims")

    # Save output
    output_path = script_dir / "extracted-claims.json"
    extractor.save_claims(unique_claims, output_path)
    print(f"\nClaims saved to: {output_path}")

    # Print summary
    by_category = extractor._count_by_category(unique_claims)
    print("\nClaims by category:")
    for category, count in sorted(by_category.items()):
        print(f"  {category}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
