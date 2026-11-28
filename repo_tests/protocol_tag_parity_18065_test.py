# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every bracket marker the backend emits must be one the frontend strips (#18065).

The frontend cannot import Python, so its list is a second copy by necessity.
This makes the copy checkable instead of hoping: a family added to
``thought_markers.BRACKET_MARKER_FAMILIES`` without being taught to
``llmProtocolTags.ts`` reaches a reader as raw text, which is the defect class
this issue exists for.

SUBSET, not equality. The frontend also strips ``DEBUG`` and ``SOURCES``, which
no backend module declares or produces -- stripping a marker that never arrives
is harmless, rendering one that does is not.
"""

from __future__ import annotations

import importlib.util
import re

from repo_tests._paths import repo_root

# One canonical spelling for the repo root (#15925) -- re-deriving it from
# `__file__` is what the guard in `one_repo_root_spelling_15925_test.py` exists
# to stop, and it caught this file on its first push.
_ROOT = repo_root()
FRONTEND_MODULE = _ROOT / "autobot-frontend" / "src" / "utils" / "llmProtocolTags.ts"
BACKEND_MODULE = _ROOT / "autobot-backend" / "chat_workflow" / "thought_markers.py"

#: Matches the exported const array, e.g.
#: `export const PROTOCOL_BRACKET_TAGS = ['THOUGHT', 'PLANNING'] as const`
_FRONTEND_LIST_RE = re.compile(r"export\s+const\s+PROTOCOL_BRACKET_TAGS\s*=\s*\[(?P<body>[^\]]*)\]", re.DOTALL)


def _frontend_families() -> set[str]:
    source = FRONTEND_MODULE.read_text(encoding="utf-8")
    match = _FRONTEND_LIST_RE.search(source)
    assert match is not None, (
        f"PROTOCOL_BRACKET_TAGS not found in {FRONTEND_MODULE.name} -- the extractor "
        "found nothing to judge, which must fail rather than pass vacuously"
    )
    return {token.strip().strip("'\"") for token in match.group("body").split(",") if token.strip()}


def _backend_families() -> set[str]:
    spec = importlib.util.spec_from_file_location("thought_markers_parity", BACKEND_MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.BRACKET_MARKER_FAMILIES)


def test_the_extractors_find_something_to_compare() -> None:
    """CONTROL, asserted first. An empty set on either side makes the subset test pass."""
    frontend, backend = _frontend_families(), _backend_families()
    assert "THOUGHT" in frontend, f"frontend list parsed as {sorted(frontend)}"
    assert "THOUGHT" in backend, f"backend list read as {sorted(backend)}"
    assert len(backend) >= 2, f"backend declares only {sorted(backend)}"


def test_every_backend_marker_family_is_stripped_by_the_frontend() -> None:
    frontend, backend = _frontend_families(), _backend_families()
    missing = _missing_families(backend, frontend)
    assert missing == [], (
        f"the frontend does not strip {missing}; a marker this backend emits would "
        f"render as raw text. Add it to PROTOCOL_BRACKET_TAGS in {FRONTEND_MODULE.name} "
        "and to the regexes beside it."
    )


#: The detector under test, lifted out so a FIXTURE can be fed to it rather than
#: only the live repository. Without this the parity test could only ever say
#: "the tree is currently consistent" -- it could not show that it NOTICES
#: inconsistency, which is the property being claimed.
def _missing_families(backend: set[str], frontend: set[str]) -> list[str]:
    return sorted(backend - frontend)


def test_the_detector_trips_on_a_missing_family_and_not_on_a_covered_one() -> None:
    """CONTRAST PAIR, required of every detector by the repo's path instructions.

    One fixture should trip it and one should not. Proving the current tree is
    consistent is not the same as proving the check works: a detector that
    returned `[]` unconditionally would pass every other test in this file.
    """
    covered = _missing_families({"THOUGHT", "PLANNING"}, {"THOUGHT", "PLANNING", "DEBUG"})
    assert covered == [], f"a fully covered backend set tripped the detector: {covered}"

    absent = _missing_families({"THOUGHT", "PLANNING"}, {"THOUGHT"})
    assert absent == ["PLANNING"], f"the detector missed an absent family, got {absent}"

    # And the degenerate input that would make the real test vacuous.
    assert _missing_families(set(), set()) == []
    assert _missing_families({"THOUGHT"}, set()) == ["THOUGHT"]


def test_each_declared_backend_family_has_a_compiled_pattern() -> None:
    """The declared set must describe the code, not drift beside it."""
    source = BACKEND_MODULE.read_text(encoding="utf-8")
    for family in sorted(_backend_families()):
        assert re.search(rf"{family}_TAG_PATTERN\s*=\s*re\.compile", source), (
            f"{family} is declared in BRACKET_MARKER_FAMILIES but has no "
            f"{family}_TAG_PATTERN -- the set names a family nothing parses"
        )
