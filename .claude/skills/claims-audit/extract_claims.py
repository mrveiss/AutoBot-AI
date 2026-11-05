#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Standalone CLI: run as `python3 .claude/skills/claims-audit/<script>.py`, where
# `autobot_shared` is not importable, so stdlib logging stands in for get_logger.
logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s\)]+")
_LINK_LINE_RE = re.compile(r"^\[.*\]\(https?://.*\)$")
_URL_ONLY_LINE_RE = re.compile(r"^https?://.*$")

CompiledPattern = Tuple[str, Dict[str, Any], "re.Pattern[str]"]


class ClaimExtractor:
    """Extract claims from documentation using pattern matching."""

    def __init__(self, patterns_dir: Path, repo_root: Path = None):
        self.patterns_dir = patterns_dir
        self.repo_root = repo_root
        self.patterns = self._load_patterns()
        self._compiled = self._compile_patterns()
        self._any_pattern = self._combine_patterns()
        self.claims = []

    def _load_patterns(self) -> Dict[str, Any]:
        """Load all pattern files from patterns directory."""
        patterns = {}
        for pattern_file in self.patterns_dir.glob("*.json"):
            category = pattern_file.stem
            with open(pattern_file, "r", encoding="utf-8") as f:
                patterns[category] = json.load(f)
        return patterns

    def _compile_patterns(self) -> List[CompiledPattern]:
        """Every pattern compiled once, in load order, with the flags the scan uses (#20805)."""
        return [
            (category, pattern_def, re.compile(pattern_def["pattern"], re.IGNORECASE))
            for category, pattern_data in self.patterns.items()
            for pattern_def in pattern_data.get("patterns", [])
        ]

    def _combine_patterns(self) -> Optional["re.Pattern[str]"]:
        """One alternation of every pattern, used only to skip lines no pattern matches.

        It never produces claims: an alternation reports non-overlapping
        matches, so two patterns matching the same text would yield one claim
        instead of two. As a yes/no test it is exact -- ``search`` finds a
        match if and only if at least one alternative matches in the line.
        """
        if not self._compiled:
            return None
        alternatives = "|".join(f"(?:{regex.pattern})" for _, _, regex in self._compiled)
        return re.compile(alternatives, re.IGNORECASE)

    def _relativize(self, file_path: Path) -> str:
        """Path relative to ``repo_root`` where that is known, else the path as given.

        Never the bare basename. The whole output of this stage is
        ``file:line`` citations a reader is expected to open, and every tree in
        this repository has a ``README.md`` in it -- dropping the directory
        turns a precise citation into an ambiguous one without saying so, and
        the issues ``file_issues.py`` raises from it point nowhere (#14986).
        """
        if self.repo_root and file_path.is_relative_to(self.repo_root):
            return str(file_path.relative_to(self.repo_root))
        return str(file_path)

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
            if in_code_block or self._is_skipped_line(line):
                continue
            file_claims.extend(self._claims_in_line(line, line_num, file_path))

        return file_claims

    def _is_skipped_line(self, line: str) -> bool:
        """Empty lines, URL-only and badge lines, and short headers carry no claim."""
        stripped = line.strip()
        if not stripped:
            return True
        if self._is_url_line(line) or self._is_badge_line(line):
            return True
        # Headers are usually metadata, skip short ones
        return stripped.startswith("#") and len(stripped) < 100

    def _claims_in_line(self, line: str, line_num: int, file_path: Path) -> List[Dict[str, Any]]:
        """Every pattern's matches in one line, minus matches inside URLs and noise."""
        if self._any_pattern is None or not self._any_pattern.search(line):
            return []
        url_spans: Optional[List[Tuple[int, int]]] = None
        claims = []
        for category, pattern_def, regex in self._compiled:
            for match in regex.finditer(line):
                if url_spans is None:
                    url_spans = [m.span() for m in _URL_RE.finditer(line)]
                # Skip matches that are inside URLs
                if any(start <= match.start() < end for start, end in url_spans):
                    continue
                # Skip very short matches that might be noise
                if len(match.group(0).strip()) < 2:
                    continue
                claims.append(self._claim(category, pattern_def, line, match, line_num, file_path))
        return claims

    def _claim(
        self,
        category: str,
        pattern_def: Dict[str, Any],
        line: str,
        match: "re.Match[str]",
        line_num: int,
        file_path: Path,
    ) -> Dict[str, Any]:
        """One claim record, in the shape the verify stage reads."""
        return {
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

    def _is_url_line(self, line: str) -> bool:
        """Check if line is primarily a URL."""
        stripped = line.strip()
        return bool(_LINK_LINE_RE.match(stripped)) or bool(_URL_ONLY_LINE_RE.match(stripped))

    def _is_badge_line(self, line: str) -> bool:
        """Check if line is a badge."""
        return "![" in line and "badge.svg" in line

    def extract_from_directory(self, dir_path: Path, glob_pattern: str = "**/*.md") -> List[Dict[str, Any]]:
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Determine paths
    script_dir = Path(__file__).parent
    patterns_dir = script_dir / "patterns"
    repo_root = script_dir.parent.parent.parent  # .claude/skills/claims-audit -> repo root

    if not patterns_dir.exists():
        logger.error("Error: Patterns directory not found: %s", patterns_dir)
        sys.exit(1)

    # Extract claims
    extractor = ClaimExtractor(patterns_dir, repo_root)
    logger.info("Extracting claims from %s...", repo_root)
    claims = extractor.extract_all(repo_root)
    logger.info("Found %d total claims", len(claims))

    # Deduplicate
    unique_claims = extractor.deduplicate_claims(claims)
    logger.info("After deduplication: %d unique claims", len(unique_claims))

    # Save output
    output_path = script_dir / "extracted-claims.json"
    extractor.save_claims(unique_claims, output_path)
    logger.info("\nClaims saved to: %s", output_path)

    # Print summary
    by_category = extractor._count_by_category(unique_claims)
    logger.info("\nClaims by category:")
    for category, count in sorted(by_category.items()):
        logger.info("  %s: %d", category, count)

    return 0


if __name__ == "__main__":
    sys.exit(main())
