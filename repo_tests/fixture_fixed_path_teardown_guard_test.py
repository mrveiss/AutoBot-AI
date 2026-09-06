# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test fixture that creates AND removes a fixed filesystem path (#15785).

    @pytest.fixture
    def temp_allowed_dir(tmp_path):                       # tmp_path taken, ignored
        test_dir = Path("/tmp/autobot/test_security")     # fixed, shared, process-wide
        test_dir.mkdir(parents=True, exist_ok=True)
        yield test_dir
        shutil.rmtree(test_dir)                           # unconditional

Two concurrent shards running this fixture at once delete each other's
directory: shard A's teardown removes the directory shard B is mid-test with.
In ``mcp_security_test.py`` that turned a dangling symlink chain into one that
*resolved* under the allowed root, which flipped a security assertion from
"blocked" to "an escape got through" -- the wrong answer was "the security
control failed" (#15785's own writeup). Fixed in #15772 by giving the leaf a
per-test suffix from ``tmp_path.name``.

The control-flow model the scanner is built on -- one scope-walking
primitive, which nested bodies the fixture reaches, and which bindings no
path can observe -- lives in ``fixture_fixed_path_teardown_flow.py``
(#15810, #15811).

The AST scanner itself lives in ``fixture_fixed_path_teardown_guard.py``, a
plain (non-``_test.py``) sibling module (the same split as
``sys_modules_leak_guard.py`` / ``sys_modules_leak_guard_test.py``), so the
scanner's own growth does not also have to fit under this module's line
budget. This module documents the guard's rationale and carries the
assertions that run it over the live tree; every synthetic contrast pair --
and the write-up of the defect each one closes -- lives in
``fixture_fixed_path_teardown_guard_contrast_test.py`` (which calls and
decorators are seen at all),
``fixture_fixed_path_teardown_guard_derivation_test.py`` (how a name earns
"derived") and ``fixture_fixed_path_teardown_guard_reachability_test.py``
(which nested bodies are live code), the same split as
``ansible_manifest_resolution_contrast_test.py``, so no module has to fit all
of it under ``check_python_file_size.py``'s MAX_LINES.

THE DISCRIMINATOR IS CREATE-AND-REMOVE, NOT A BARE FIXED PATH
-----------------------------------------------------------------
``api/codebase_analytics/endpoints/report_scoping_test.py:384``
(``Path("/tmp/does-not-need-to-exist")``) and
``services/knowledge/code_graph_provenance_test.py:95``
(``Path("/tmp/unused-13508.json")``) are both fixed, shared paths -- and both
are inert: neither is inside a ``@pytest.fixture`` at all, and neither ever
calls ``mkdir``/``rmtree``. This guard only ever inspects functions decorated
with ``@pytest.fixture``, so both are out of scope by construction, not by an
exemption list.

WHY "UNCONDITIONAL" MATTERS: ``tmp_root_exists`` IN THE SAME FILE
----------------------------------------------------------------------
``mcp_security_test.py``'s own ``tmp_root_exists`` fixture also creates a
fixed, non-``tmp_path``-derived path (``Path(TMP_ROOT)``) and also calls
``shutil.rmtree`` in its teardown -- but only inside ``if created: ...``,
never unconditionally, and cleans up by diffing pre-existing entries the rest
of the time. That is the same shape #15772's fix uses for a genuinely
required fixed root (``ALLOWED_DIRECTORIES`` permits ``/tmp/autobot/`` and
``tmp_path`` sits outside it) -- gating the destructive call behind a
condition, or deriving the leaf from ``tmp_path``, is exactly what stops two
shards from deleting each other's tree. ``_collect_calls`` tracks whether a
call sits inside an ``ast.If``/ternary and only counts an *unguarded* removal
call as the hazard, which is why ``tmp_root_exists`` is not flagged while the
pre-#15772 ``temp_allowed_dir`` is (see the contrast module's own pair). Both
fixtures are pinned against the real source below, by name.

WHY THE FIXTURE IS SYNTHETIC, NOT THE LIVE VIOLATION SET
---------------------------------------------------------
The one known instance was fixed in #15772; the live population is zero
(measured below). Seeding this guard's pass/fail from that population would
make it vacuous today and break the moment a violation reappears -- the trap
#15762 records. Every contrast pair is a literal fixture source the contrast
module writes itself; nothing in the pass/fail path is seeded from the tree.

REACH, NOT FINDINGS (the vacuity floor)
------------------------------------------
The violation count is zero either way, so a scanner that silently examined
no fixtures would print the identical clean line as one that examined every
fixture in the tree. ``_MIN_EXPECTED_FIXTURES_SCANNED`` binds the floor to how
many ``@pytest.fixture`` functions were actually found, not to what they did --
same shape as ``core_router_auth_guard_test.py``'s
``_MIN_EXPECTED_CORE_ROUTERS``. Measured at 1,216+ fixtures across every
tracked ``.py`` file (fixtures live in plain test modules and in
``conftest.py``, so the scan is not limited to ``*_test.py`` filenames); the
floor sits comfortably below that.

DEFECTS CLOSED, AND THE PAIRS THAT PROVE THEY STAY CLOSED
------------------------------------------------------------
Eight defects have been closed in this guard since #15785 -- an unseen decorator
alias, an if/else that removed on every branch, a ``tmp_path`` read that never
reached the path, a tuple assignment that leaked derivation across targets, a
call keyword that laundered a fixed path argument, two traversals that walked
into nested ``def``/``lambda`` scopes, and a name credited as derived on one
assignment while another gave it a fixed path, a registered finalizer whose
removal sat in a scope the scanner declined to enter, and a dead binding
counted against the name that overwrote it. Each has a two-sided contrast
pair, and all of them live in
``fixture_fixed_path_teardown_guard_contrast_test.py``,
``fixture_fixed_path_teardown_guard_derivation_test.py`` or
``fixture_fixed_path_teardown_guard_reachability_test.py`` with the write-up
of the defect they close.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests.fixture_fixed_path_teardown_guard import (
    _MIN_EXPECTED_FIXTURES_SCANNED,
    _REPO,
    _is_violation,
    _iter_pytest_fixtures,
    _scan_repo,
)


@pytest.fixture(scope="module")
def scan_result():
    return _scan_repo()


class TestScanIsNotVacuous:
    """A guard that silently examines nothing would report a clean sweep too."""

    def test_fixture_reach_meets_floor(self, scan_result):
        examined, _violations, _unreadable = scan_result
        assert examined >= _MIN_EXPECTED_FIXTURES_SCANNED, (
            f"only {examined} pytest fixtures were examined, below the recorded floor of "
            f"{_MIN_EXPECTED_FIXTURES_SCANNED} -- every assertion below is vacuous if the "
            "scan itself silently collapsed"
        )

    def test_no_tracked_source_is_unreadable_by_this_guard(self, scan_result):
        _examined, _violations, unreadable = scan_result
        assert (
            not unreadable
        ), f"these tracked sources could not be parsed, so this guard saw NONE of their fixtures: {unreadable}"


class TestFixedPathTeardownGuard:
    def test_no_fixture_creates_and_unconditionally_removes_a_fixed_path(self, scan_result):
        _examined, violations, _unreadable = scan_result
        assert not violations, (
            f"{violations} -- each fixture creates a path that is not derived from tmp_path "
            "(or another per-test unique source) and unconditionally removes it in teardown. "
            "Concurrent shards running this fixture collide (#15785). Derive the leaf from "
            "tmp_path, or gate the removal behind a check the way "
            "mcp_security_test.py's tmp_root_exists does"
        )


class TestKnownInertPlaceholdersStayUnflagged:
    """#15785's own AC: neither placeholder may quietly become a fixture this guard must judge."""

    @pytest.mark.parametrize(
        "relative_path,needle",
        [
            ("autobot-backend/api/codebase_analytics/endpoints/report_scoping_test.py", "does-not-need-to-exist"),
            ("autobot-backend/services/knowledge/code_graph_provenance_test.py", "unused-13508.json"),
        ],
    )
    def test_placeholder_path_is_not_inside_a_fixture(self, relative_path, needle):
        path = _REPO / relative_path
        source = path.read_text(encoding="utf-8")
        needle_line = next(i + 1 for i, line in enumerate(source.splitlines()) if needle in line)
        fixture_lines = {
            lineno
            for func in _iter_pytest_fixtures(ast.parse(source))
            for lineno in (getattr(n, "lineno", None) for n in ast.walk(func))
            if lineno is not None
        }
        assert needle_line not in fixture_lines, (
            f"{relative_path}:{needle_line} is now inside a pytest fixture -- re-evaluate it "
            "against this guard's create-and-remove discriminator instead of assuming it stays inert"
        )


class TestRealFixtureRegressionPins:
    """Pins the guard's classification against the actual fixtures #15772 and #13598 shipped.

    Not the seed for pass/fail (see module docstring) -- an extra check against
    real code already known to be on each side of the line, so a change to the
    discriminator itself is caught here as well as by the synthetic pair below.
    """

    @pytest.mark.parametrize(
        "fixture_name,expected_violation",
        [
            ("temp_allowed_dir", False),  # #15772: unique leaf under the allowed root
            ("temp_forbidden_dir", False),  # tmp_path-derived directly
            ("tmp_root_exists", False),  # #13598: if-guarded / diff-based cleanup, not unconditional
        ],
    )
    def test_mcp_security_fixtures_are_classified_correctly(self, fixture_name, expected_violation):
        path = _REPO / "autobot-backend" / "mcp" / "mcp_security_test.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        (func,) = (f for f in _iter_pytest_fixtures(tree) if f.name == fixture_name)
        assert _is_violation(func) is expected_violation
