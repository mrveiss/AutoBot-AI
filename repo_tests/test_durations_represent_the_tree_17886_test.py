# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The committed shard durations must represent the tree they split (#17886).

``repo_tests/stable_shard.py`` balances CI shards on weights from
``.test_durations`` / ``.test_durations_slm``, and its argument is that a weight
only has to be *proportional* to cost. On 2026-10-03 that premise was false: the
files dated from 2026-08-17, and **48% of the backend test modules and 57% of the
SLM ones carried no weight at all** -- 334 of 339 ``repo_tests`` modules among
them. The splitter balanced a 338-second shadow of a ~98-minute suite.

The weekly ``test-durations.yml`` run measured correctly the whole time. Its
``land`` job could not open the refresh PR (the repository did not permit GitHub
Actions to create pull requests), so every refresh was pushed to a branch and
stranded, and a red 3am cron is nobody's alert. The drift was silent because
nothing failed when the record went stale. This is that missing failure.

WHAT IT MEASURES: for each durations file, the fraction of git-tracked test
modules under the roots its generator collects that have **no** recorded timing.
The roots are parsed from ``test-durations.yml`` itself, so this check cannot
disagree with the generator about what it collects.

WHAT IT CANNOT SEE: whether a recorded timing is still *accurate* -- only whether
a module is represented at all. A module whose tests are all deselected by the
generator's marker filter is legitimately absent; that is part of the allowed
fraction, which is why the ceiling is not zero.

WHAT IT DETECTS: catastrophic staleness, not moderate drift. A fresh refresh
measured 2.9% (backend) and 3.3% (SLM) unrepresented six days after it ran; the
stale files measured 48.3% and 57.1%. 15% is about five times the fresh value and
allows weeks of ordinary growth between weekly refreshes. What it does NOT claim:
anything about how well the splitter balances at 14.9% -- that was never measured.
A shrink-only ratchet on the measured fraction does not fit either: the fraction
legitimately rises every week and drops at each refresh. Raise the ceiling only
with a measurement, never to make red go green.
"""

from __future__ import annotations

import json
import re

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_WORKFLOW = ".github/workflows/test-durations.yml"

#: Largest fraction of collected test modules allowed to carry no recorded timing.
MAX_UNREPRESENTED_FRACTION = 0.15

#: Reach floor: the backend file's roots held 2,459 test modules and the SLM file's
#: 245 when this was written. Far below either means the enumeration broke. (An
#: empty enumeration would raise ZeroDivisionError rather than pass, but the floor
#: names the real cause instead of a division error.)
_MIN_TRACKED_MODULES = {".test_durations": 1500, ".test_durations_slm": 150}

#: One ``python -m pytest <roots> ... --durations-path <file>`` invocation.
_INVOCATION = re.compile(
    # `(?!\s*python -m pytest)` stops the search at the next invocation, so an
    # invocation with no --durations-path cannot lend its roots to the next one's path.
    r"python -m pytest \\\n\s+(?P<roots>[^\n\\]+?)\s*\\\n(?:(?!\s*python -m pytest)[^\n]*\n)*?"
    r"\s+--durations-path (?P<path>\S+)"
)
_TEST_MODULE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def generator_roots(workflow_text: str) -> dict[str, list[str]]:
    """Durations file -> the roots the generator collects for it."""
    return {m["path"]: m["roots"].split() for m in _INVOCATION.finditer(workflow_text)}


def unrepresented_fraction(durations: dict[str, float], tracked_modules: set[str]) -> float:
    """Fraction of *tracked_modules* with no timing in *durations* (keys are pytest node ids)."""
    recorded = {node_id.split("::", 1)[0] for node_id in durations}
    return len(tracked_modules - recorded) / len(tracked_modules)


def _tracked_test_modules(roots: list[str]) -> set[str]:
    return {p for p in tracked_paths(repo_root(), *roots) if _TEST_MODULE.search(p)}


def _invocations() -> dict[str, list[str]]:
    return generator_roots((repo_root() / _WORKFLOW).read_text(encoding="utf-8"))


def test_the_generator_invocations_are_found():
    """If the workflow's shape changes, this fails first -- not the coverage check, vacuously."""
    invocations = _invocations()
    assert set(invocations) == set(_MIN_TRACKED_MODULES), f"parsed {sorted(invocations)} from {_WORKFLOW}"
    assert all(invocations.values()), f"an invocation parsed with no roots: {invocations}"


@pytest.mark.parametrize("durations_file", sorted(_MIN_TRACKED_MODULES))
def test_the_committed_durations_represent_the_tree(durations_file: str):
    tracked = _tracked_test_modules(_invocations()[durations_file])
    assert (
        len(tracked) >= _MIN_TRACKED_MODULES[durations_file]
    ), f"enumerated {len(tracked)} test modules for {durations_file} -- the walk broke"
    durations = json.loads((repo_root() / durations_file).read_text(encoding="utf-8"))

    fraction = unrepresented_fraction(durations, tracked)

    assert fraction <= MAX_UNREPRESENTED_FRACTION, (
        f"{durations_file}: {fraction:.1%} of {len(tracked)} collected test modules carry no timing "
        f"(ceiling {MAX_UNREPRESENTED_FRACTION:.0%}). The shard splitter is balancing a shadow of the suite. "
        f"Refresh it: run {_WORKFLOW} (workflow_dispatch) and merge the PR it opens."
    )


def test_a_stale_or_truncated_record_is_refused():
    """The check must be able to fail: a record covering a fraction of the tree is red."""
    tracked = {f"repo_tests/m{i}_test.py" for i in range(100)}
    fresh = {f"repo_tests/m{i}_test.py::test_a": 0.1 for i in range(97)}
    truncated = {f"repo_tests/m{i}_test.py::test_a": 0.1 for i in range(5)}

    assert unrepresented_fraction(fresh, tracked) <= MAX_UNREPRESENTED_FRACTION
    assert unrepresented_fraction(truncated, tracked) > MAX_UNREPRESENTED_FRACTION


def test_the_roots_parser_reads_a_real_shaped_invocation():
    text = (
        "          python -m pytest \\\n"
        "            autobot-backend repo_tests libs \\\n"
        "            -n auto --dist loadscope \\\n"
        "            --durations-path .test_durations \\\n"
    )
    assert generator_roots(text) == {".test_durations": ["autobot-backend", "repo_tests", "libs"]}


@pytest.mark.parametrize(
    "mangled",
    [
        # no --durations-path: a pytest call that stores no durations is not a generator
        "          python -m pytest \\\n            autobot-backend repo_tests \\\n            -n auto \\\n",
        # roots on the pytest line itself, not the continuation line the generator uses
        "          python -m pytest autobot-backend repo_tests \\\n            --durations-path .test_durations \\\n",
    ],
)
def test_the_roots_parser_rejects_a_shape_it_does_not_understand(mangled: str):
    """The parser must be seen to fail, or a loosened regex could match the wrong thing silently."""
    assert generator_roots(mangled) == {}


def test_an_unrecorded_invocation_does_not_lend_its_roots_to_the_next():
    """Adjacent invocations stay separate: roots belong to the invocation that names the path."""
    text = (
        "          python -m pytest \\\n            unrecorded_root \\\n            -n auto \\\n"
        "          python -m pytest \\\n            slm_root \\\n            --durations-path .test_durations_slm \\\n"
        "          python -m pytest \\\n            backend_root \\\n            --durations-path .test_durations \\\n"
    )
    assert generator_roots(text) == {".test_durations_slm": ["slm_root"], ".test_durations": ["backend_root"]}
