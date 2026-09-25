# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase validation must not report what it did not check (#17089).

Two defects, one report. "Phase 6: Enhanced UI/UX" read **100% complete** while
the UI was visibly inconsistent, because:

1. ``--ci-mode`` skips the endpoint, service and feature checks -- correctly, CI
   has no live stack -- but skipping removed them from the DENOMINATOR as well,
   and the phase figure is ``passed / total``. Phase 6's two surviving checks
   were "``App.vue`` exists" and "``package.json`` exists". 2/2 = 100%.
2. 14 of the 15 paths in the feature-check lambdas pointed at the
   pre-reorganization layout (``src/``, ``backend/``, ``autobot-vue/``), so even
   with a live stack those checks could only ever fail. #7496's comment says the
   paths were refreshed; it refreshed the criteria dict and not the lambdas.

WHY THE PATH GUARD READS THE SOURCE WITH ``ast`` INSTEAD OF IMPORTING IT.
``phase_validation_system`` imports ``aiohttp``, ``psutil``, ``requests`` and
``autobot_shared.redis_client`` at module scope. Importing it here would make a
path guard depend on a live-ish environment, and importing
``autobot_shared.redis_client`` has side effects -- it generates and writes
secret key material when none is configured. A guard must not mutate the tree it
guards. So the paths are read as data, the way ``tools/lint/prepush_selection``
reads its record.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_SYSTEM = Path("autobot-infrastructure/shared/scripts/phase_validation_system.py")
_POLICY = Path("autobot-infrastructure/shared/scripts/phase_score.py")

#: The `files`/`directories` entries across all ten phases. A floor, not an
#: equality: phases may gain criteria. Below it, the parse found less than the
#: tree holds and the assertions built on it would be weaker than they look.
_MIN_CRITERIA_PATHS = 30

#: Path literals inside the feature-check lambdas. 15 today; the floor exists so
#: a lambda shape this parser stops recognising fails loudly instead of
#: silently checking nothing -- the vacuity failure that let 14 dead paths sit
#: unnoticed.
_MIN_LAMBDA_PATHS = 12


def _tree() -> ast.Module:
    return ast.parse((repo_root() / _SYSTEM).read_text(encoding="utf-8"))


def _criteria_paths() -> list[tuple[str, str]]:
    """``(phase, path)`` for every `files`/`directories` entry in PHASE_CRITERIA."""
    block = next(
        stmt
        for node in ast.walk(_tree())
        if isinstance(node, ast.ClassDef)
        for stmt in node.body
        if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "PHASE_CRITERIA" for t in stmt.targets)
    )
    found: list[tuple[str, str]] = []
    for phase_key, criteria in zip(block.value.keys, block.value.values):
        phase = ast.literal_eval(phase_key)
        for key, value in zip(criteria.keys, criteria.values):
            if ast.literal_eval(key) not in ("files", "directories"):
                continue
            for element in value.elts:
                found.append((phase, ast.literal_eval(element)))
    return found


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "text"`` assignments, for resolving path pieces.

    The feature checks compose paths as ``root / _SHARED_SCRIPTS / "x.py"``, so a
    scanner that only collects string literals sees ``"x.py"`` and misses the
    directory. Resolving the constant is what keeps this guard looking at the
    same path the code builds.
    """
    constants: dict[str, str] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant):
            if isinstance(stmt.value.value, str):
                constants[target.id] = stmt.value.value
    return constants


def _joined_path(node: ast.AST, constants: dict[str, str]) -> str | None:
    """Flatten a ``root / a / b`` division chain into ``"a/b"``.

    ``None`` when any operand is neither a string constant nor a known
    module-level string -- an unresolvable piece must not silently yield a
    shorter path that then "exists".
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return "" if node.id == "root" else constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _joined_path(node.left, constants)
        right = _joined_path(node.right, constants)
        if left is None or right is None:
            return None
        return f"{left}/{right}".lstrip("/")
    return None


def _lambda_paths() -> list[tuple[int, str]]:
    """``(line, path)`` for every repo-relative path a feature-check lambda builds."""
    tree = _tree()
    constants = _module_string_constants(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Lambda):
            continue
        for inner in ast.walk(node):
            if not (isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Div)):
                continue
            joined = _joined_path(inner, constants)
            if joined and "/" in joined and not joined.startswith(("/api", "http", "//")):
                found.append((inner.lineno, joined))
    # A nested chain yields its prefix as well as the whole; keep only the
    # longest path per line, which is the one the code actually opens.
    longest: dict[int, str] = {}
    for line, path in found:
        if len(path) > len(longest.get(line, "")):
            longest[line] = path
    return sorted(longest.items())


def _criteria_gate_lists() -> list[tuple[str, list[str]]]:
    """``(phase, authoritative_gates)`` for phases that declare them."""
    block = next(
        stmt
        for node in ast.walk(_tree())
        if isinstance(node, ast.ClassDef)
        for stmt in node.body
        if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "PHASE_CRITERIA" for t in stmt.targets)
    )
    out: list[tuple[str, list[str]]] = []
    for phase_key, criteria in zip(block.value.keys, block.value.values):
        for key, value in zip(criteria.keys, criteria.values):
            if ast.literal_eval(key) == "authoritative_gates":
                out.append((ast.literal_eval(phase_key), [ast.literal_eval(e) for e in value.elts]))
    return out


def _policy():
    """``phase_score`` loaded by path -- it imports nothing but the stdlib.

    Registered in ``sys.modules`` before execution because ``dataclasses``
    resolves ``cls.__module__`` through it; without that the class body raises.
    """
    spec = importlib.util.spec_from_file_location("phase_score", repo_root() / _POLICY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase_score"] = module
    spec.loader.exec_module(module)
    return module


class TestEveryReferencedPathExists:
    """AC2: a criterion pointing at a path that is gone measures nothing."""

    def test_the_parse_found_the_criteria_paths(self) -> None:
        paths = _criteria_paths()
        assert len(paths) >= _MIN_CRITERIA_PATHS, (
            f"only {len(paths)} criteria paths parsed (floor {_MIN_CRITERIA_PATHS}); "
            "PHASE_CRITERIA's shape changed and the existence check below is now weaker "
            "than it appears"
        )

    def test_every_criteria_path_exists(self) -> None:
        root = repo_root()
        missing = [f"{phase}: {path}" for phase, path in _criteria_paths() if not (root / path).exists()]
        assert not missing, "phase criteria reference paths that do not exist:\n  " + "\n  ".join(missing)

    def test_the_parse_found_the_lambda_paths(self) -> None:
        paths = _lambda_paths()
        assert len(paths) >= _MIN_LAMBDA_PATHS, (
            f"only {len(paths)} lambda paths parsed (floor {_MIN_LAMBDA_PATHS}); the feature "
            "checks changed shape and this guard has stopped seeing them, which is how 14 "
            "dead paths went unnoticed"
        )

    def test_every_feature_check_path_exists(self) -> None:
        root = repo_root()
        missing = [
            f"{_SYSTEM}:{line} -> {path}" for line, path in _lambda_paths() if not (root / path.split("*")[0]).exists()
        ]
        assert (
            not missing
        ), "feature checks point at paths that do not exist, so they can only ever " "report False:\n  " + "\n  ".join(
            missing
        )


class TestSkippedCanNeverReadAsComplete:
    """AC1/AC4: the inversion that made a 2-of-2 file sweep read as 100% done."""

    def test_a_phase_with_a_skipped_group_is_not_complete_even_at_100_percent(self) -> None:
        # Phase 6's exact CI shape: both structural checks pass, every live
        # group skipped. This is the case that reported "100% complete".
        score = _policy().PhaseScore(ran=2, passed=2, skipped=("endpoints", "ui_features"))

        assert score.percentage == 100.0, "the ratio of what ran is still reported"
        assert score.complete is False, "a phase with skipped checks must never read as complete"
        assert score.status == "structural-presence-only"

    def test_the_report_omits_completion_percentage_entirely_when_anything_was_skipped(self) -> None:
        # Absent, not zero and not null: a consumer reaching for it gets a
        # KeyError rather than a number it would have believed.
        report = _policy().PhaseScore(ran=2, passed=2, skipped=("endpoints",)).as_report()

        assert "completion_percentage" not in report
        assert report["structural_presence_percentage"] == 100.0
        assert report["not_checked"] == {"endpoints": _policy().NOT_CHECKED}
        assert "endpoints" in report["why_not_complete"]

    def test_a_full_run_still_reports_completion(self) -> None:
        # The control. Without it, every assertion above is satisfied by a
        # policy that refuses to report completion under any circumstances.
        report = _policy().PhaseScore(ran=9, passed=9).as_report()

        assert report["completion_percentage"] == 100.0
        assert report["complete"] is True
        assert report["status"] == "complete"
        assert "not_checked" not in report

    @pytest.mark.parametrize("passed,expected", [(0, 0.0), (1, 50.0), (2, 100.0)])
    def test_the_ratio_is_of_what_ran(self, passed: int, expected: float) -> None:
        assert _policy().PhaseScore(ran=2, passed=passed).percentage == expected

    def test_nothing_ran_is_zero_and_not_complete(self) -> None:
        score = _policy().PhaseScore(ran=0, passed=0)

        assert score.percentage == 0.0
        assert score.complete is False


class TestTheOverallFiguresDistinguishTheTwo:
    """The top-level keys the CI gate and the step summary read."""

    def test_overall_maturity_is_none_when_a_group_was_skipped(self) -> None:
        policy = _policy()
        skipped = policy.PhaseScore(ran=2, passed=2, skipped=("endpoints",))

        aggregate = policy.overall([(skipped, 100.0)])

        assert aggregate["overall_maturity"] is None, "maturity was not measured, so it is not a number"
        assert aggregate["structural_presence"] == 100.0
        assert aggregate["measures"] == "structural presence only"
        assert aggregate["phases_complete"] == 0

    def test_ready_for_production_is_none_rather_than_false_when_unassessed(self) -> None:
        # False would read as "assessed and failed" to anything rendering this.
        policy = _policy()
        aggregate = policy.overall([(policy.PhaseScore(ran=2, passed=2, skipped=("services",)), 100.0)])

        assert aggregate["ready_for_production"] is None

    def test_a_full_run_produces_a_maturity_figure(self) -> None:
        policy = _policy()
        aggregate = policy.overall([(policy.PhaseScore(ran=10, passed=9), 100.0)])

        assert aggregate["overall_maturity"] == 90.0
        assert aggregate["measures"] == "completion"
        assert aggregate["ready_for_production"] is True

    def test_weighting_follows_the_declared_weights(self) -> None:
        policy = _policy()
        full = policy.PhaseScore(ran=1, passed=1)
        empty = policy.PhaseScore(ran=1, passed=0)

        assert policy.overall([(full, 75.0), (empty, 25.0)])["structural_presence"] == 75.0


class TestTheSkipListStaysInStepWithWhatIsSkipped:
    """The stale-list failure mode, applied to the skip list itself."""

    def test_every_feature_type_the_validator_iterates_is_in_live_stack_groups(self) -> None:
        # `_validate_phase_features` iterates a hard-coded list of feature
        # types. If one is added there and not here, that group would be
        # silently skipped in CI and never reported as unchecked -- the same
        # under-reporting this issue is about, one level down.
        source = (repo_root() / _SYSTEM).read_text(encoding="utf-8")
        function = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "_validate_phase_features"
        )
        listed = next(
            [ast.literal_eval(e) for e in stmt.value.elts]
            for stmt in ast.walk(function)
            if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "feature_types" for t in stmt.targets)
        )

        assert listed, "parsed no feature types -- the validator's shape changed"
        groups = set(_policy().LIVE_STACK_GROUPS)
        assert set(listed) <= groups, (
            "these feature types are iterated by _validate_phase_features but absent from "
            f"LIVE_STACK_GROUPS, so skipping them would go unreported: {sorted(set(listed) - groups)}"
        )


class TestEveryMethodItCallsOnItselfExists:
    """Every ``self._x()`` resolves to a ``def _x`` in the class.

    Added because writing this PR broke it: removing a superseded method with a
    slice bounded by the next ``    def `` swallowed the ``    async def`` that
    followed it, deleting ``_validate_phase_features`` while its call site
    stayed. ``python -m py_compile`` passed -- Python resolves attribute names at
    call time, so a missing method is invisible until the line runs, and in
    ``--ci-mode`` that line is inside the branch CI does not take.

    A guard belongs here rather than in the commit that caused it: the file is
    974 lines of methods calling each other, run by a workflow whose failure
    mode is a zero-maturity fallback that looks like a legitimate result.
    """

    def test_no_self_call_points_at_a_missing_method(self) -> None:
        source = (repo_root() / _SYSTEM).read_text(encoding="utf-8")
        tree = ast.parse(source)

        defined = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        }

        assert called, "parsed no self-calls at all -- this guard would be vacuous"
        missing = sorted(called - defined)
        assert not missing, (
            f"{_SYSTEM} calls methods on itself that are not defined: {missing}. "
            "py_compile cannot see this; only running the line can."
        )


class TestTheProgressionManagerDoesNotPromoteOnPresence:
    """The consumer where this defect had teeth (#17089).

    ``phase_progression_manager`` calls ``validate_all_phases()`` and then
    decided a phase was completed from a bare percentage -- so a ``--ci-mode``
    run, in which only file-existence checks execute, could mark a phase
    complete and PROGRESS it on "the files are present". The percentage it read
    no longer exists when anything was skipped, and this pins that it asks the
    honest field instead of reintroducing a numeric read.
    """

    _CONSUMER = Path("autobot-backend/phase_progression_manager.py")

    def test_it_gates_on_complete_and_not_on_a_bare_percentage(self) -> None:
        source = (repo_root() / self._CONSUMER).read_text(encoding="utf-8")

        assert (
            "from scripts.phase_validation_system import PhaseValidator" in source
        ), "this guard's premise is that this module consumes the validator; the import is gone"
        assert '["completion_percentage"]' not in source, (
            "phase_progression_manager reads `completion_percentage` from validation results "
            "again. That key is absent whenever a check group was skipped, so this both "
            "KeyErrors and -- if defaulted -- promotes phases on file presence (#17089)."
        )
        assert source.count('["complete"]') >= 2, (
            "both progression decisions must consult `complete`, which is False whenever " "anything was skipped"
        )


class TestAPhaseVerifiedElsewhereReportsNoScore:
    """AC3: the UI/UX phase links to the real gates and reports no percentage.

    Whether a UI is consistent, responsive and internationalised is not a
    question a file-existence sweep can answer at any percentage. The owner's
    objection was to a number, so the fix is to stop producing one for that
    phase rather than to produce a better-labelled one.
    """

    _UI_PHASE = "Phase 6: Enhanced UI/UX"

    def test_the_ui_phase_declares_the_workflows_that_verify_it(self) -> None:
        gates = dict(_criteria_gate_lists()).get(self._UI_PHASE)

        assert gates, f"{self._UI_PHASE} declares no authoritative_gates"
        for gate in gates:
            assert (repo_root() / gate).exists(), f"{self._UI_PHASE} names a workflow that does not exist: {gate}"

    def test_a_deferring_phase_reports_neither_percentage(self) -> None:
        report = (
            _policy()
            .PhaseScore(ran=2, passed=2, skipped=("endpoints",), defers_to=(".github/workflows/frontend-test.yml",))
            .as_report()
        )

        assert not [
            key for key in report if "percentage" in key
        ], f"a deferring phase must publish no figure of its own; got {sorted(report)}"
        assert report["status"] == "deferred-to-dedicated-gates"
        assert report["complete"] is False
        assert report["authoritative_gates"] == [".github/workflows/frontend-test.yml"]
        assert "frontend-test" in report["why_no_score"]

    def test_a_deferring_phase_contributes_nothing_to_the_aggregate(self) -> None:
        # Otherwise its number still reaches the CI gate through the average,
        # and "reports no score" would be true of the phase and false of the run.
        policy = _policy()
        deferring = policy.PhaseScore(ran=2, passed=2, defers_to=(".github/workflows/frontend-test.yml",))
        scored = policy.PhaseScore(ran=4, passed=2)

        aggregate = policy.overall([(deferring, 100.0), (scored, 100.0)])

        assert aggregate["structural_presence"] == 50.0, "the scored phase alone, not averaged with a 100"
        assert aggregate["phases_excluded_from_score"] == 1
        assert aggregate["verified_by_dedicated_gates"] == [".github/workflows/frontend-test.yml"]

    def test_a_non_deferring_phase_still_contributes(self) -> None:
        # The control: without it, an `overall` that excluded everything would
        # satisfy the assertion above.
        policy = _policy()
        aggregate = policy.overall([(policy.PhaseScore(ran=4, passed=3), 100.0)])

        assert aggregate["structural_presence"] == 75.0
        assert aggregate["phases_excluded_from_score"] == 0
