# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push hook must not run both backends in one pytest session (#16069).

`pytest.ini` states the rule in as many words:

    #13084: autobot-backend/ and autobot-slm-backend/ each define top-level
    packages with identical names (api, services, user_management, middleware,
    migrations). Running ALL of testpaths in ONE pytest invocation makes
    whichever backend collects first bind those dotted names in sys.modules for
    the rest of the session, breaking the other backend's own tests. A full
    local/CI run MUST use two separate invocations.

CI obeys it. The pre-push hook did not: it collected every changed test into one
`$all_py_tests` and ran a single `pytest` over it, so any changeset touching both
trees was verified in a shape CI never runs and `pytest.ini` forbids.

**The failure it produced looked like someone else's bug.** `autobot-slm-backend`'s
conftest installs its stubs at import time, so in a combined session `sqlalchemy`,
`sqlalchemy.orm`, `sqlalchemy.ext.asyncio`, `models` and `models.database` remain
`MagicMock`s while `repo_tests` collects afterwards. The sys.modules leak guard saw
54 leaked keys and blocked the push -- correctly, and for a condition the changeset
had not introduced: the conftest was byte-identical to base. Two sessions spent time
on the conftest before anyone read the invocation.

That the conftest should also stop leaking is true and is #16069's other half. This
half is narrower and comes first: the hook must stop *producing* the state, rather
than the guard being asked to tolerate it.

These tests run the hook's OWN split expressions rather than a copy of them. A
reimplementation here would agree with itself and prove nothing -- the same reason
the timeout tests (#15985) execute the helper instead of grepping for its message.
"""

from __future__ import annotations

import re
import subprocess

from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"

_SLM_PREFIX = "autobot-slm-backend/"

#: Pull the two assignments out of the hook and run them, so the partition under
#: test is the shipped one.
_ASSIGN = re.compile(
    r"^\s*(slm_py_tests|other_py_tests)=\$\(echo \"\$all_py_tests\" \| (?P<filter>.+?) \|\| true\)\s*$",
    re.MULTILINE,
)


def _split(paths: list[str]) -> dict[str, list[str]]:
    source = _HOOK.read_text(encoding="utf-8")
    filters = {m.group(1): m.group("filter") for m in _ASSIGN.finditer(source)}
    assert set(filters) == {"slm_py_tests", "other_py_tests"}, (
        f"the hook no longer assigns both groups the expected way: found {sorted(filters)}. "
        "If the split moved, move this test with it -- do not delete it."
    )

    out = {}
    for group, expr in filters.items():
        # Feed the list on stdin rather than interpolating it into the script.
        # An earlier version embedded a Python repr, so bash received the two
        # characters \\n instead of newlines, every case collapsed to a single
        # line, and the harness "passed" while testing nothing. The filter under
        # test is the grep expression; stdin exercises exactly that.
        completed = subprocess.run(
            ["bash", "-c", f"{expr} || true"],
            input="\n".join(paths),
            capture_output=True,
            text=True,
            check=True,
        )
        out[group] = [line for line in completed.stdout.splitlines() if line]
    return out


def test_a_mixed_changeset_is_partitioned_not_merged() -> None:
    """The case that broke: one changeset touching both trees."""
    paths = [
        "autobot-slm-backend/conftest_thing_test.py",
        "autobot-slm-backend/services/role_units_test.py",
        "repo_tests/some_guard_test.py",
        "autobot-backend/api/thing_test.py",
    ]
    groups = _split(paths)

    assert groups["slm_py_tests"] == [
        "autobot-slm-backend/conftest_thing_test.py",
        "autobot-slm-backend/services/role_units_test.py",
    ]
    assert groups["other_py_tests"] == [
        "repo_tests/some_guard_test.py",
        "autobot-backend/api/thing_test.py",
    ]

    assert not set(groups["slm_py_tests"]) & set(groups["other_py_tests"]), "the groups overlap"
    assert sorted(groups["slm_py_tests"] + groups["other_py_tests"]) == sorted(paths), (
        "the split dropped or duplicated a path -- a test silently not run is the "
        "failure mode this whole hook exists to prevent"
    )
    assert not any(p.startswith(_SLM_PREFIX) for p in groups["other_py_tests"])


def test_a_single_tree_changeset_still_runs_as_one_invocation() -> None:
    """The common case must not gain a second, empty pytest run."""
    only_other = _split(["repo_tests/a_test.py", "autobot-backend/b_test.py"])
    assert only_other["slm_py_tests"] == []
    assert len(only_other["other_py_tests"]) == 2

    only_slm = _split(["autobot-slm-backend/a_test.py"])
    assert only_slm["other_py_tests"] == []
    assert only_slm["slm_py_tests"] == ["autobot-slm-backend/a_test.py"]


def test_a_lookalike_prefix_is_not_swept_into_the_slm_group() -> None:
    """`autobot-slm-backend` is a directory, not a substring.

    A path merely containing the name -- a fixture under repo_tests, say --
    belongs to the other group. Anchoring is the difference, and a matcher that
    loses its anchor is how the commit-trailer re-derivation reported 3,444
    violations (see RATCHET_BASELINES.md rule 5).
    """
    groups = _split(
        [
            "repo_tests/fixtures/autobot-slm-backend/decoy_test.py",
            "autobot-slm-backend/real_test.py",
        ]
    )
    assert groups["slm_py_tests"] == ["autobot-slm-backend/real_test.py"]
    assert groups["other_py_tests"] == ["repo_tests/fixtures/autobot-slm-backend/decoy_test.py"]


def test_the_hook_no_longer_runs_one_pytest_over_every_changed_test() -> None:
    """The defect itself, pinned so it cannot come back by simplification.

    Structural rather than behavioural on purpose: the two assignments above can
    be correct while a stray `pytest $all_py_tests` still runs beside them, and
    that combination would pass every test in this file.
    """
    source = _HOOK.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "python3 -m pytest" in line and "$all_py_tests" in line
    ]
    assert not offenders, (
        "the hook runs one pytest invocation over every changed test again, which "
        f"pytest.ini forbids for the two backends (#13084, #16069): {offenders}"
    )
