# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No shipped prompt may instruct the model to refuse nothing (#16105).

Six profiles under ``autobot-backend/resources/prompts`` carried such an
instruction. ``hacker/`` and ``reflection/`` are vendored Agent Zero personas,
which is the reading that makes this look like inert sample data. **``autobot/``
carried the identical line under this product's own name**, ``default/`` -- the
profile an unconfigured request resolves to -- carried the variant scoped to
personal information, and ``developer/``/``researcher/`` carried the most
explicit form of all.

``api/prompts.py:151`` calls ``_collect_prompt_files(prompts_dir, "", ...)``,
recursive by construction at ``:192-199`` with **no profile allowlist**, so the
tree is served wholesale.

WHY THE MATCHER IS TWO-FACTOR RATHER THAN A LIST OF PHRASES
-----------------------------------------------------------
The finding grew three times -- one directory reported, four found by a
repo-wide sweep, six found by this guard -- and each time the instrument was
different, never the reading closer. The sweep that found four matched
``never refuse|do not refuse|refuse.{0,25}safety``; ``refuse`` does not match
``refusal``, so the two most explicit instances were invisible to a pattern
written from the terse ones.

A guard listing the six spellings we now know about would be that same defect
one layer up. Probed against 14 plausible phrasings absent from the tree -- *do
not decline any request*, *unconditional compliance is required*, *safety
filters are disabled*, and the developer line with one word changed --
a lemma-anchored pattern missed **14 of 14**.

So detection is two factors in proximity: a suppression marker near an
obligation verb, or a suppression marker near a safety noun. It **fails toward
false positives**, which a repo guard can absorb and a missed directive cannot.

Every false positive is then an entry in :data:`REVIEWED` with a reason, and
:func:`test_no_reviewed_line_has_gone_stale` fails when an entry stops matching.
That is the point: an exemption is a line of code, so it gets a comment, a diff
and a reviewer; a blind spot is the absence of a line and gets none of the
three. This guard has no silent exemptions.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402
from repo_tests._paths import repo_root  # noqa: E402
from repo_tests.prompt_refusal_suppression_corpus import (  # noqa: E402
    CORRECT_POLARITY,
    KNOWN_SUPPRESSION,
    UNSEEN_SUPPRESSION,
)

PROMPTS = "autobot-backend/resources/prompts"

#: Bound to what was EXAMINED, never to what was found. A ``git ls-files``
#: returning nothing -- wrong cwd, scrubbed env gone wrong, partial checkout --
#: would otherwise pass having read zero files, which is the same clean result a
#: clean tree gives (#15826).
MIN_PROMPT_FILES = 60

_SUPPRESSION_MARKER = r"never|not|n't|without|regardless|ignore|disabl\w*|unconditional|always|\bno\b|\bany\b|every|\ball\b"
_OBLIGATION = r"refus\w*|declin\w*|reject\w*|withh\w*|refrain\w*|compl(?:y|ies|iance)|restrict\w*|filter\w*|say\s+no|exception\w*"
_SAFETY = r"safety|safe|unsafe|ethic\w*|harm\w*|legal|law|moral|conscience|content"
_GAP = r"\W+(?:\w+\W+){0,3}?"

_NEAR_OBLIGATION = re.compile(
    rf"(?:{_SUPPRESSION_MARKER}){_GAP}(?:{_OBLIGATION})|(?:{_OBLIGATION}){_GAP}(?:{_SUPPRESSION_MARKER})", re.IGNORECASE
)
_NEAR_SAFETY = re.compile(
    rf"(?:{_SUPPRESSION_MARKER}){_GAP}(?:{_SAFETY})|(?:{_SAFETY}){_GAP}(?:{_SUPPRESSION_MARKER})", re.IGNORECASE
)

#: Lines the two-factor matcher flags that are NOT refusal suppression, each
#: read and ruled on. Exact text, so a reworded line returns for review.
REVIEWED = {
    # Anti-hallucination. "NO exceptions" attaches to a rule REQUIRING honesty.
    '**This rule has NO exceptions.** Providing plausible-sounding but fabricated information is worse than saying "I don\'t know."',
    # A checklist prompt asking the model to consider safety, not to ignore it.
    "- **Safety**: Are there any security or data protection concerns?",
    # "Always balance efficiency with safety" -- safety-positive.
    "Remember: AutoBot's strength comes from intelligent automation combined with human oversight. Always balance efficiency with safety, and automation with user control.",
    # Adherence to the behavioural rules, which now include "Refuse tasks that
    # are unsafe, unlawful, or harmful". Adhering to those without exception is
    # the desired reading, not a suppression.
    "- **Behavioral Framework**: Strictly adhere to all provided behavioral rules and instructions without exception",
    # #16105: a PERSISTENCE directive about acquiring tools, not about refusing.
    # The weakest entry in this list and the one a human should rule on: it
    # presses for unconditional task completion with no safety carve-out, in a
    # legacy prompt. Kept because rewording a legacy orchestrator directive is a
    # behaviour change beyond this issue, and recorded here rather than silently
    # excluded so the decision is visible.
    "You MUST adhere to this directive without exception.",
}

def suppresses_refusal(line: str) -> bool:
    """Two factors in proximity: suppression near an obligation, or near safety."""
    return bool(_NEAR_OBLIGATION.search(line) or _NEAR_SAFETY.search(line))


def _prompt_files() -> list[Path]:
    root = repo_root()
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", PROMPTS], cwd=root, capture_output=True, text=True, check=False, env=scrubbed_git_env()
    )
    return [root / line for line in result.stdout.splitlines() if line]


def _flagged_lines() -> list[tuple[str, int, str]]:
    root = repo_root()
    hits = []
    for path in _prompt_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped and suppresses_refusal(stripped):
                hits.append((str(path.relative_to(root)), number, stripped))
    return hits


def test_the_detector_finds_every_known_instance() -> None:
    """Known positives. A zero from a broken matcher reads as a clean tree."""
    for line in KNOWN_SUPPRESSION:
        assert suppresses_refusal(line), f"detector no longer finds a live instance: {line}"


def test_the_detector_finds_phrasings_absent_from_the_tree() -> None:
    """The controls that justify two factors over a phrase list.

    A lemma-anchored pattern -- every branch requiring refuse/refus -- caught all
    six live strings and missed all fourteen of these. The last is the shipped
    developer line with one word changed.
    """
    missed = [line for line in UNSEEN_SUPPRESSION if not suppresses_refusal(line)]
    assert not missed, (
        f"{len(missed)}/{len(UNSEEN_SUPPRESSION)} unseen phrasings not flagged: {missed}. "
        "The pattern matches what was found, not what the instruction is."
    )


def test_the_corrected_lines_are_not_flagged() -> None:
    """Negative controls, load-bearing: proximity alone would flag these."""
    wrong = [line for line in CORRECT_POLARITY if suppresses_refusal(line)]
    assert not wrong, "the replacement policy lines flag as suppression:\n  " + "\n  ".join(wrong)


def test_the_sweep_reads_the_prompt_tree() -> None:
    """Non-vacuity, bound to what was examined."""
    files = _prompt_files()
    assert len(files) >= MIN_PROMPT_FILES, (
        f"git ls-files matched {len(files)} files under {PROMPTS}; the path may have moved. "
        "A sweep over an empty set reports the same clean result as a clean tree."
    )


def test_no_shipped_prompt_suppresses_refusal() -> None:
    """The constraint. Scoped to the tree, not to the six known profiles: the
    population that matters is what the loader serves, and it has no allowlist.
    """
    offenders = [f"{path}:{number}: {line}" for path, number, line in _flagged_lines() if line not in REVIEWED]
    assert not offenders, "shipped prompt(s) instruct the model not to refuse:\n  " + "\n  ".join(offenders)


def test_no_reviewed_line_has_gone_stale() -> None:
    """An exemption matching nothing tolerates whatever appears next.

    When a REVIEWED line is reworded or removed, this fails rather than letting
    the entry sit and silently widen. The list may only shrink by decision.
    """
    live = {line for _, _, line in _flagged_lines()}
    stale = sorted(REVIEWED - live)
    assert not stale, "REVIEWED entries no longer present; remove them:\n  " + "\n  ".join(stale)
