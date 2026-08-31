# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workflow comment must not cite a closed issue/PR as *live* justification (#15333 AC4).

This is the second occurrence of the exact same defect. #15252's dead
integration-test path survived because its comment attributed the gap to
closed #734; #15333 found ``code-quality.yml`` attributing 4133 + 1281
suppressed mypy errors to closed #7105. Both read, at a glance, like a
tracked and accepted state — a reader checking whether the gap is accounted
for finds a closed ticket and moves on.

The tractable subset, mirroring the pattern in both known instances: "tracked"
followed within four words by "#N"/"GH#N" ("tracked in #N", "tracked by #N",
"tracked for resolution in #N"). A character-width window instead of a
word-count cap over-matches unrelated prose — e.g. a step literally named
"Block newly tracked symlinks ... (#14137)" is not a live-tracking citation.
Scanning for *any* ``#N`` mention and failing on every closed one is not
viable — 234 of the 293 resolvable references under ``.github/workflows`` at
authorship time were closed, because most are ordinary historical
attribution ("fixed by #N", "RETIRED (#N)", "see #N for why"), not live
justification. That volume is itself evidence a bare occurrence check would
be ignored or worked around within a week, which is worse than no check.

Resolution needs the GitHub API, so this guard SKIPS — visibly, not
silently — when ``gh`` is unavailable or unauthenticated, per #15333's own
note that this is offline-hostile by nature ("one API call per distinct
reference").
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONS_DIR = REPO_ROOT / ".github" / "actions"

# "tracked" followed by up to four words then "#N" / "GH#N", e.g. "tracked in
# GH#7105", "tracked by #5263 (22 in 10 files ...)", "tracked for resolution in
# GH#7105". Deliberately one-directional (word before reference) and word-capped
# rather than character-capped — see module docstring for why a wider window
# (any "#N" within N characters of "tracked") over-matched unrelated prose such
# as a step named "Block newly tracked symlinks ... (#14137)".
TRACKED_REFERENCE_PATTERN = re.compile(r"\btracked\b(?:\s+[A-Za-z]+){0,4}?\s*(?:GH#|#)(\d+)", re.IGNORECASE)
MIN_EXPECTED_REFERENCES = 3
GRAPHQL_CHUNK_SIZE = 50

# Findings from building this guard, not yet resolved (#15346) — the citation
# is real and the issue it names is genuinely closed, but repointing it
# requires a judgment call (re-measure the backlog, decide whether the
# comment's own stated trigger condition should now fire) outside this
# guard's scope. Recorded here, not silently dropped: both entries carry the
# tracking issue and must be removed once #15346 lands its fix.
DELIBERATELY_EXEMPT = {
    (".github/workflows/code-quality.yml", 5263): "#15346 — 'After #5263 closes, swap to full-scan mode'",
    (".github/workflows/ssot-coverage.yml", 14371): "#15346 — hardcoded-values baseline backlog",
}


@dataclass(frozen=True)
class Reference:
    path: Path
    line_no: int
    number: int
    raw: str


def _workflow_files() -> list[Path]:
    files = sorted(WORKFLOW_DIR.glob("*.yml"))
    files += sorted(ACTIONS_DIR.glob("*/action.yml"))
    return files


def _extract_tracked_references(files: list[Path]) -> list[Reference]:
    references: list[Reference] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in TRACKED_REFERENCE_PATTERN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            references.append(Reference(path, line_no, int(match.group(1)), match.group(0)))
    return references


# The two defects this guard exists to catch, as literal text, plus the prose
# that made a wider pattern unusable. The repository scan below cannot pin this:
# once #7105 is repointed, that shape leaves the tree entirely, so a later
# "simplification" of the pattern could keep the count floor green while
# silently losing the shape the guard was built for.
_MATCHES = [
    ("tracked in GH#7105", 7105),
    ("tracked by #5263 (22 in 10 files)", 5263),
    ("tracked for resolution in #734", 734),
    ("# a path tracked in #14371 without updating", 14371),
]
_NON_MATCHES = [
    "Block newly tracked symlinks in the pre-commit hook (#14137)",
    "see #13637",
    "tracked separately; the follow-up work is not numbered here",
]


def test_the_pattern_matches_both_known_defect_shapes():
    """The premise of the narrowing: it still catches what it was built for."""
    missed = []
    for text, expected in _MATCHES:
        match = TRACKED_REFERENCE_PATTERN.search(text)
        if match is None or int(match.group(1)) != expected:
            missed.append(f"{text!r} -> {match.group(0) if match else None}")
    assert not missed, "the pattern stopped matching live-tracking citations: " + "; ".join(missed)


def test_the_pattern_rejects_prose_that_merely_contains_tracked():
    """A wider pattern produced 234 false positives out of 293; keep it narrow."""
    caught = [t for t in _NON_MATCHES if TRACKED_REFERENCE_PATTERN.search(t) is not None]
    assert not caught, f"the pattern widened back into ordinary prose: {caught}"


def test_the_scan_actually_finds_tracked_references():
    """A regex that matched nothing would make the guard below vacuous, not clean."""
    references = _extract_tracked_references(_workflow_files())
    unique = {(r.path, r.number) for r in references}
    assert len(unique) >= MIN_EXPECTED_REFERENCES, (
        f"Only found {len(unique)} 'tracked ... #N' citations under .github/workflows "
        f"and .github/actions — expected at least {MIN_EXPECTED_REFERENCES}. The "
        "extraction pattern is broken, not the repository."
    )


def _repo_slug() -> str | None:
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            check=True,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None
    slug = result.stdout.strip()
    return slug if slug and "/" in slug else None


def _resolve_chunk(owner: str, name: str, chunk: list[int]) -> dict[int, str] | None:
    fields = "\n".join(
        f"n{number}: issueOrPullRequest(number: {number}) "
        "{ __typename ... on Issue { state } ... on PullRequest { state } }"
        for number in chunk
    )
    query = f'query {{ repository(owner: "{owner}", name: "{name}") {{ {fields} }} }}'
    try:
        # NOT check=True: a NOT_FOUND alias makes gh exit 1 even though the
        # other aliases in the same chunk resolved fine — the partial JSON on
        # stdout is exactly what this needs, so a raised CalledProcessError
        # would discard real data for one bad reference in the batch.
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    repo_data = payload.get("data", {}).get("repository")
    if repo_data is None:
        return None
    return {number: node["state"] for number in chunk if (node := repo_data.get(f"n{number}"))}


def _resolve_states(owner: str, name: str, numbers: list[int]) -> dict[int, str] | None:
    states: dict[int, str] = {}
    for start in range(0, len(numbers), GRAPHQL_CHUNK_SIZE):
        chunk_states = _resolve_chunk(owner, name, numbers[start : start + GRAPHQL_CHUNK_SIZE])
        if chunk_states is None:
            return None
        states.update(chunk_states)
    return states


def _is_exempt(reference: Reference) -> bool:
    key = (str(reference.path.relative_to(REPO_ROOT)), reference.number)
    return key in DELIBERATELY_EXEMPT


def test_no_workflow_comment_cites_a_closed_issue_as_live_tracking():
    """#15333 AC4: fail (visibly), never pass by having found nothing to check."""
    if shutil.which("gh") is None:
        pytest.skip("gh CLI is not installed — cannot resolve issue/PR state, skipping visibly")
    references = [r for r in _extract_tracked_references(_workflow_files()) if not _is_exempt(r)]
    slug = _repo_slug()
    if slug is None:
        pytest.skip("gh could not resolve the repository slug (no auth/network) — skipping visibly")
    owner, name = slug.split("/", 1)
    states = _resolve_states(owner, name, sorted({r.number for r in references}))
    if states is None:
        pytest.skip("gh api graphql failed (no auth/network) — skipping visibly")
    violations = sorted(
        f"{r.path.relative_to(REPO_ROOT)}:{r.line_no} cites {r.raw!r} — #{r.number} is CLOSED"
        for r in references
        if states.get(r.number) == "CLOSED"
    )
    assert not violations, "Closed issue cited as live tracking justification:\n" + "\n".join(violations)
