# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deployment script's inline check must not fabricate its own result (#14867).

Split out of ``deployment_script_imports_resolve_test`` (#14518): that module
carries the import layer and the call layer, and the reporting layer below is a
third, independent concern with its own detector, its own exemption table and
its own positive/negative controls. Both read the scripts through the one
extractor in ``deployment_script_scan``.
"""

from __future__ import annotations

import re

import pytest
from repo_tests.deployment_script_scan import (
    PY_BLOCK_PATTERNS,
    SCRIPT_DIR,
    count_blocks,
    shell_scripts,
)

# --------------------------------------------------------------------------
# The reporting layer (#14867, #14877). Resolving the import and letting the
# error reach stderr are both necessary and still not sufficient: what a caller
# downstream READS must also change when the check could not run. #14868 fixed
# these imports and removed the `2>/dev/null`, but left `|| echo "{}"`, so the
# monitor still answers a failed check with a value that reads as "no findings".
# That is the specific thing #14866 cost: `0|0|0` violations reported *because*
# the imports were broken.
# --------------------------------------------------------------------------

# A literal that impersonates a successful measurement. Deliberately not every
# `|| echo` — a fallback that says "unavailable" is fine; one that says "0" or
# "{}" is a fabricated clean result.
_SENTINEL = re.compile(r'^(?:[0-9|.]+|UNKNOWN|N/?A|\{\}|\[\]|""|null)$', re.IGNORECASE)
_FALLBACK_ECHO = re.compile(r'\|\|\s*(?:echo|printf)\s+(["\']?)([^"\'\n;]*)\1')

# Scripts still doing this, each with its tracking issue. Same self-guarding
# contract as _KNOWN_BROKEN: asserted STILL fabricating, so a fix forces the
# entry out rather than leaving the guard quietly narrower than it claims.
#
# #14880 emptied it: access_control_monitor.sh was the last entry, and its three
# sentinels are gone. Empty is the goal state, which is why the discovery floor
# below no longer asserts that the sweep FOUND something — see
# test_the_fabrication_detector_still_fires.
_KNOWN_FABRICATING: dict[str, str] = {}


def _fabricated_in_text(text: str) -> list[tuple[int, str]]:
    """(line, sentinel) for each python block in ``text`` answered by a sentinel.

    Split out from the sweep so the detector can be driven directly by the
    positive control below. With no script fabricating any more, "the sweep
    found offenders" can no longer serve as proof the matcher still works — and
    a matcher that quietly stops matching reports every script clean.

    Reuses the two block regexes above rather than scanning a single line. The
    first draft matched ``python3 -c`` to end-of-line, which finds nothing for a
    MULTI-LINE block — the fallback sits after the closing quote, several lines
    down. It reported zero fabricated results on a file that had three, and only
    a positive control caught it.
    """
    found: list[tuple[int, str]] = []
    for pattern in PY_BLOCK_PATTERNS:
        for match in pattern.finditer(text):
            newline = text.find("\n", match.end())
            tail = text[match.end() : newline if newline != -1 else len(text)]
            echo = _FALLBACK_ECHO.search(tail)
            if echo and _SENTINEL.match(echo.group(2).strip()):
                found.append((text[: match.start()].count("\n") + 1, echo.group(2).strip()))
    return found


def _fabricated_results() -> tuple[list[tuple[str, int, str]], int]:
    """(sites answering a failed python check with a sentinel, blocks seen)."""
    sites: list[tuple[str, int, str]] = []
    blocks = 0
    for script in shell_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        blocks += count_blocks(text)
        rel = str(script.relative_to(SCRIPT_DIR))
        sites.extend((rel, line, value) for line, value in _fabricated_in_text(text))
    return sites, blocks


# Assembled from fragments so this file never contains the literal shape it
# bans — a fixture quoting a banned pattern trips the lint that reads it.
_SAMPLE_SENTINELS = ["{" + "}", "0|0" + "|0", "UNK" + "NOWN"]


@pytest.mark.parametrize("sentinel", _SAMPLE_SENTINELS)
def test_the_fabrication_detector_still_fires(sentinel: str) -> None:
    """Positive control, replacing 'the sweep found offenders'.

    That floor was only meaningful while a script was still fabricating. Now
    that none are, an extractor that stopped matching would sail through the
    check below having read nothing. This drives the detector against both block
    shapes directly, so it fails when the detector breaks rather than when the
    codebase regresses.
    """
    inline = 'value=$(python3 -c "import sys" || ' + f'echo "{sentinel}")\n'
    multiline = 'value=$(python3 -c "\nimport sys\nprint(sys.argv)\n" || ' + f'echo "{sentinel}")\n'

    for sample, shape in ((inline, "single-line"), (multiline, "multi-line")):
        assert count_blocks(sample) == 1, f"the {shape} block extractor no longer matches its own shape"
        hits = _fabricated_in_text(sample)
        assert hits, f"the detector no longer flags {sentinel!r} on a {shape} block"
        assert hits[0][1] == sentinel


def test_a_legitimate_fallback_is_not_flagged() -> None:
    """Negative control: the rule is 'impersonates a measurement', not 'has a fallback'."""
    sample = 'value=$(python3 -c "import sys" || echo "unavailable")\n'
    assert count_blocks(sample) == 1
    assert not _fabricated_in_text(sample), "a fallback that says 'unavailable' is the fix, not the bug"


def test_the_fabrication_sweep_reached_the_scripts() -> None:
    """Discovery floor — an extractor that stops matching reports clean."""
    _, blocks = _fabricated_results()
    assert blocks >= 20, (
        f"only extracted {blocks} inline python blocks — the matcher has "
        "regressed and the check below would pass having read nothing"
    )


def test_no_inline_check_fabricates_its_own_result() -> None:
    """A check that could not run must not report a reassuring value (#14867)."""
    sites, _ = _fabricated_results()
    offenders = [
        f"{rel}:{line}  answers a failed python block with {value!r}"
        for rel, line, value in sites
        if rel not in _KNOWN_FABRICATING
    ]
    assert not offenders, (
        "a failed check must be distinguishable from a clean one by what it "
        "REPORTS, not only by what reaches stderr. Emit an explicit error and a "
        "non-zero exit status instead of a sentinel (#14867):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("rel,issue", sorted(_KNOWN_FABRICATING.items()))
def test_each_fabrication_exemption_is_still_broken(rel: str, issue: str) -> None:
    """An obsolete exemption exempts nothing, and is this check's positive control."""
    assert (SCRIPT_DIR / rel).is_file(), f"{rel} moved or was deleted — update this exemption ({issue})"
    sites, _ = _fabricated_results()
    assert any(r == rel for r, _, _ in sites), (
        f"{rel} no longer fabricates a result, so the exemption ({issue}) is "
        "obsolete — remove it from _KNOWN_FABRICATING so the script is guarded again"
    )
