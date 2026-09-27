# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The real scanner over the real shapes: three silenced, one kept (#17668).

`comment_blanking_test.py` tests the blanker. This tests the **scanner**, because
those are different claims and only the second one is the finding.

Why it exists as its own file: the fix silenced three of four live findings, and a
fix that silenced *all four* would be indistinguishable from a correct one if only
the three were checked. Structural proxies -- "code after a closed block is still
scanned", "a plain call is untouched" -- do not settle it either; they show the
mechanism is capable of keeping a call, not that it kept *this* call. Raised as a
merge condition on #17670, and correct: it needs the scanner run, not a read.

So this asserts both directions through `FrontendAPICallScanner._scan_file`:

    documentation  -> reported before the fix, absent after
    the real call  -> reported before the fix, still reported after

The "before" side is reconstructed by scanning the same content with comments left
intact, which is what the prefix test did for every shape that did not start with a
marker. That keeps the two sides comparable without needing the old revision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.codebase_analytics.api_endpoint_scanner import FrontendAPICallScanner

#: Each case is (relative path, the JSDoc/comment lines that must go, the real
#: call lines that must stay). Taken from the live panel's four findings.
_CASES = [
    ("autobot-frontend/src/composables/useFileDownload.ts", [11, 16], []),
    ("autobot-frontend/src/utils/apiErrorHandler.ts", [222], []),
    ("autobot-frontend/src/views/slm/ThemeManagerView.vue", [], [35]),
]


def _repo_root() -> Path:
    # api/codebase_analytics/<this file> -> autobot-backend -> repo root
    return Path(__file__).resolve().parents[3]


def _scan_production(rel: str) -> dict[int, str]:
    """`{line: path}` from the **production entry point**, `_scan_file`.

    Calling `_scan_file` rather than re-running its loop is the whole point: an
    earlier version of this helper applied `blank_comments` and the call patterns
    itself, so it would have passed even if `_scan_file` stopped blanking
    altogether. A verification that reimplements what it verifies tests its own
    copy -- the same defect as using a private regex instead of the scanner's, one
    level up (#17670 review).
    """
    root = _repo_root()
    scanner = FrontendAPICallScanner(root)
    return {call.line_number: call.path for call in scanner._scan_file(root / rel)}


def _scan_prefix_era(rel: str) -> dict[int, str]:
    """`{line: path}` as the pre-fix scanner saw it -- a deliberate reconstruction.

    Kept separate from the production path and named as a reconstruction, because it
    cannot be taken from `_scan_file` any more: that now blanks unconditionally. It
    reproduces what the old prefix test did for every shape not starting with a
    marker, which is all three false positives.
    """
    root = _repo_root()
    scanner = FrontendAPICallScanner(root)
    source = (root / rel).read_text(encoding="utf-8")

    found: dict[int, str] = {}
    for i, line in enumerate(source.splitlines(), 1):
        for pattern in _patterns():
            for match in pattern.finditer(line):
                call = scanner._parse_api_call(match, line, i, rel)
                if call:
                    found[i] = call.path
    return found


def _patterns():
    from api.codebase_analytics import api_endpoint_scanner as mod

    return mod._API_CALL_PATTERNS


@pytest.mark.parametrize(("rel", "doc_lines", "real_lines"), _CASES)
def test_documentation_is_silenced_and_real_calls_survive(rel: str, doc_lines: list, real_lines: list) -> None:
    before = _scan_prefix_era(rel)
    after = _scan_production(rel)

    for line in doc_lines:
        assert line in before, f"{rel}:{line} was expected to be a pre-fix false positive"
        assert line not in after, f"{rel}:{line} is documentation and is still reported"

    for line in real_lines:
        assert line in before, f"{rel}:{line} should have been reported before the fix too"
        assert line in after, (
            f"{rel}:{line} is a real call and the fix silenced it -- a fix that "
            "silences everything is indistinguishable from one that silences noise"
        )


def test_the_one_real_finding_is_named_and_kept() -> None:
    """The fourth finding, by path and line, not by proxy.

    `POST /api/themes` at `ThemeManagerView.vue:35` is a theme upload with no
    matching backend route — the only true positive of the four. Naming it here is
    what makes "3 of 4 were false" checkable by hand rather than a claim.
    """
    after = _scan_production("autobot-frontend/src/views/slm/ThemeManagerView.vue")
    assert after.get(35) == "/api/themes"


def test_the_comparison_is_not_vacuous() -> None:
    """If the pre-fix scan found nothing, every "absent after" assertion is empty.

    `MEASUREMENT_DISCIPLINE.md`: an empty result must not read as a clean one.
    """
    total_before = sum(len(_scan_prefix_era(rel)) for rel, _, _ in _CASES)
    assert total_before >= 4, f"only {total_before} pre-fix findings -- the fixtures no longer carry the shapes"
