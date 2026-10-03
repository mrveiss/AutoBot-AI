# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The frontend size ceilings only ratchet down, and the walk really reaches the tree (#17885).

The third gate's half of the two-anchor mechanism. ``scripts/check_frontend_file_size.py``
holds one copy of the ceilings and ``frontend_file_size_ratchet_baseline.py`` the other;
``ceiling_record_parity_17872_test.py`` asserts the two are EQUAL in both directions, and this
file asserts each recorded number is still true of the file it names.

Why a third gate existed to build: nothing measured `.ts`/`.vue` length at all. The only size
hooks in `.pre-commit-config.yaml` were Python (#5060) and shell (#17353),
``function-length-check`` is ``types: [python]``, and neither frontend has an ESLint
``max-lines`` rule. A frontend file did not pass a size rule -- nothing asked.

The ceilings came from this gate's own first run, not from a number chosen in advance: 1,779
tracked files in scope, 184 over 600 lines, largest 2,947. The generated OpenAPI clients are
excluded by PREFIX rather than recorded as entries, because a 178,894-line generated file
cannot be split by its author and recording it would make the record look like a decision.
"""

from __future__ import annotations

import importlib.util

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests.frontend_file_size_ratchet_baseline import RATCHET_BASELINE

REPO_ROOT = repo_root()
HOOK_PATH = REPO_ROOT / "scripts" / "check_frontend_file_size.py"

#: Reach floor for this test's own enumeration, independent of the hook's: a walk that stopped
#: covering the frontends would report on almost nothing and call it clean (#14547).
_MIN_TRACKED = 1200


@pytest.fixture(scope="module")
def hook():
    """Load the gate by path -- scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("_check_frontend_file_size", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_records_agree_on_every_entry(hook):
    """Belt to the parity test's braces: equality here too, so neither file is the only check."""
    assert hook.KNOWN_LARGE == RATCHET_BASELINE, (
        "KNOWN_LARGE in scripts/check_frontend_file_size.py and RATCHET_BASELINE in "
        "repo_tests/frontend_file_size_ratchet_baseline.py disagree. Lower a ceiling in BOTH in "
        "the same commit: the gap between them is exactly the lines just cut, and it is spendable."
    )


def test_every_recorded_ceiling_is_still_true_of_its_file(hook):
    """The ratchet's substance: a recorded number that no longer matches is not a ceiling."""
    problems = []
    for rel, ceiling in sorted(hook.KNOWN_LARGE.items()):
        measured = hook.count_lines(REPO_ROOT / rel)
        if measured is None:
            problems.append(f"{rel}: recorded at {ceiling} but could not be read")
        elif measured != ceiling:
            problems.append(f"{rel}: recorded {ceiling}, measures {measured}")
    assert not problems, (
        "recorded ceilings no longer describe their files — lower the ones that shrank in BOTH "
        "records, and delete the ones now within the limit:\n  " + "\n  ".join(problems)
    )


def test_no_unlisted_frontend_file_is_oversized(hook):
    """The walk, not the record: a file that grew past the limit without being added must fail."""
    tracked = hook.tracked_frontend_files(REPO_ROOT)
    assert len(tracked) >= _MIN_TRACKED, f"enumerated only {len(tracked)} files — the walk broke"
    unlisted = {
        rel: n
        for rel in tracked
        if rel not in hook.KNOWN_LARGE and (n := hook.count_lines(REPO_ROOT / rel)) and n > hook.MAX_LINES
    }
    assert not unlisted, f"oversized and unrecorded — split them, do not add entries: {unlisted}"


def test_every_recorded_file_is_over_the_limit(hook):
    """An entry naming a compliant file exempts nothing while looking authoritative."""
    compliant = {rel: n for rel, n in hook.KNOWN_LARGE.items() if n <= hook.MAX_LINES}
    assert not compliant, f"these are within {hook.MAX_LINES} lines; delete their entries: {compliant}"


def test_excluded_prefixes_mirror_the_pre_commit_config(hook):
    """Two places say what is out of scope, and they must say the same thing.

    The audit walk runs independently of pre-commit, so without this the gate could flag files
    pre-commit was never configured to gate, or skip files it was.
    """
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    entry = next(h for repo in config["repos"] for h in repo.get("hooks", []) if h["id"] == "frontend-file-size")
    # `\.` in the YAML is a regex-escaped dot; the hook stores the literal prefix. Unescaping
    # rather than comparing raw strings, because the shell gate's equivalent test learned the
    # same thing -- a mirror check that fails on escaping compares spellings, not scope.
    pattern = entry["exclude"].lstrip("^").strip("()")
    declared = {part.replace("\\.", ".") for part in pattern.split("|") if part}
    assert declared == set(hook.EXCLUDED_PREFIXES), (
        f"the hook excludes {sorted(hook.EXCLUDED_PREFIXES)} and pre-commit excludes "
        f"{sorted(declared)} — widening or narrowing scope means editing both in one commit"
    )


def test_the_generated_clients_are_out_of_scope(hook):
    """Named deliberately: this is the exclusion the record would otherwise be dominated by."""
    generated = "autobot-frontend/src/types/generated/api.ts"
    assert (REPO_ROOT / generated).exists(), "the generated client moved; re-check the exclusion"
    assert generated not in hook.tracked_frontend_files(REPO_ROOT), "generated output must be excluded"
    assert generated not in hook.KNOWN_LARGE, "a generated file must not be recorded as a ceiling"


_SAMPLE = "autobot-frontend/src/App.vue"
_CEILING = RATCHET_BASELINE[_SAMPLE]


@pytest.mark.parametrize(
    ("measured", "expect"),
    [
        pytest.param(_CEILING + 1, "may not grow", id="over-ceiling"),
        pytest.param(_CEILING - 1, "under its recorded ceiling", id="under-ceiling"),
        pytest.param(600, "now within the", id="now-compliant"),
    ],
)
def test_the_three_way_verdict(hook, measured: int, expect: str):
    """All three directions fail, which is what makes it a ratchet rather than a cap."""
    message = hook.verdict(_SAMPLE, measured)
    assert message and expect in message, f"{measured} lines gave {message!r}"


def test_a_file_at_its_exact_ceiling_passes(hook):
    """The contrast case: without it the three above would pass on a gate that always complains."""
    assert hook.verdict(_SAMPLE, _CEILING) is None


def test_an_unlisted_oversized_file_is_told_to_split(hook):
    message = hook.verdict("autobot-frontend/src/views/NotRecorded.vue", hook.MAX_LINES + 1)
    assert message and "Split it" in message and "not a way in for new files" in message
