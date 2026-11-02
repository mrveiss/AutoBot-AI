# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The phase-validation report is a contract, and an absent figure is not a 0 (#17674, #17559).

WHAT BROKE. ``_output_json_results`` did not serialise the results object -- it
built a hand-written four-key projection of it. #17505 added
``structural_presence`` to the aggregate and repointed the CI gate at it, in one
change, and did not add it to the projection. The gate read ``None``, its own
``else 0`` rendered that as ``0``, and ``0 < 60`` failed ``AutoBot Phase
Validation`` on ``main`` for 17 consecutive runs. The measurement succeeded; the
transport dropped it, and then a defensive default dressed the loss up as a
score. #7496 is the same defect, two months earlier, in the same function, and
the note it left behind is on the line above the one that reintroduced it.

SO THERE ARE TWO GUARDS HERE, NOT ONE.

1. **The projection cannot drop a key.** It is now a carry-through with a
   deny-list of keys it restructures, so a key added to the aggregate reaches
   the artifact by default. ``TestNothingTheWorkflowReadsIsMissing`` derives one
   list from the workflow source and the other from the real
   ``project_report``, and compares them -- a hand-kept pair of lists is how
   this happened twice.
2. **An absent measurement cannot render as a number.** ``phase_report_figure``
   distinguishes *absent*, *null*, *unreadable* and *a real 0.0*. The last one
   is the test that matters: a guard that merely rejects falsy values has
   swapped one indistinguishable pair for another.

WHY THE POLICY MODULES ARE LOADED BY PATH. ``phase_validation_system`` imports
``aiohttp``, ``psutil``, ``requests`` and ``autobot_shared.redis_client`` at
module scope, and importing the last of those WRITES secret key material when
none is configured. A guard must not mutate the tree it guards, so the two
stdlib-only modules are loaded by path and the heavy module is read as data with
``ast`` -- the same division ``phase_validation_paths_and_skips_17089_test.py``
already makes.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines

_SCRIPTS = Path("autobot-infrastructure/shared/scripts")
_SYSTEM = _SCRIPTS / "phase_validation_system.py"
_POLICY = _SCRIPTS / "phase_score.py"
_READER = _SCRIPTS / "phase_report_figure.py"
_WORKFLOW = Path(".github/workflows/phase_validation.yml")

#: The artifact both gates read. Named once so the workflow scanners below
#: cannot drift from the file the producer actually writes.
_REPORT_FILE = "phase_validation_results.json"

#: A fixed stamp: the projection takes its timestamp as an argument precisely so
#: the same results object projects to the same report.
_STAMP = "2026-10-04T00:00:00"

#: Floor for the workflow key scan. Four top-level keys are read today. Below
#: this the regexes matched less than the file holds, and "nothing missing"
#: would mean "saw nothing" -- the failure this whole issue is about, applied to
#: its own guard.
_MIN_KEYS_READ = 4

_LOADED: Dict[str, Any] = {}


def _by_path(name: str, relative: Path):
    """Load a stdlib-only script by path, without leaving it in ``sys.modules``.

    It must be registered WHILE the body runs (``dataclasses`` resolves
    ``cls.__module__`` through it) and must not stay there: the suite's
    sys.modules leak guard fails a test file that installs a key outside
    ``repo_tests/``, and it is right to.
    """
    if name not in _LOADED:
        spec = importlib.util.spec_from_file_location(name, repo_root() / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
        _LOADED[name] = module
    return _LOADED[name]


def _policy():
    return _by_path("phase_score", _POLICY)


def _reader():
    return _by_path("phase_report_figure", _READER)


def _workflow_text() -> str:
    return (repo_root() / _WORKFLOW).read_text(encoding="utf-8")


def _system_tree() -> ast.Module:
    return ast.parse((repo_root() / _SYSTEM).read_text(encoding="utf-8"))


def _ci_mode_results() -> Dict[str, Any]:
    """A results object shaped like a real ``--ci-mode`` run.

    Both halves come from the real policy. The earlier version of this fixture
    wrote the per-phase dicts as literals, and that is how it managed to assert
    a deferring phase reports ``None`` while the live artifact carried
    ``structural_presence_percentage: 0`` -- the literal simply omitted the key
    the producer was seeding. A fixture that is hand-written on the side being
    measured can only confirm what its author already believed, so the phase
    dicts are built by ``_validate_phase``'s own two steps: the empty skeleton
    from ``_empty_phase_result``, then ``PhaseScore.as_report()`` over it.

    Every phase carries a skipped live-stack group, because ``--ci-mode``
    brings no stack up -- which is what makes ``overall_maturity`` null and
    ``structural_presence`` the only figure a gate can read.
    """
    policy = _policy()
    scored = [
        ("Phase 1: Core Infrastructure", policy.PhaseScore(ran=4, passed=4, skipped=("endpoints", "services")), 100.0),
        ("Phase 2: Knowledge Base and Memory", policy.PhaseScore(ran=3, passed=2, skipped=("services",)), 60.0),
        ("Phase 6: Enhanced UI/UX", policy.PhaseScore(ran=0, passed=0, defers_to=("frontend-quality.yml",)), 80.0),
    ]
    phases: Dict[str, Any] = {}
    for name, score, _weight in scored:
        # The same two steps `_validate_phase` performs, in the same order.
        phase = _empty_phase_skeleton(name)
        phase.update(score.as_report())
        phases[name] = phase

    results: Dict[str, Any] = {
        "timestamp": "ignored -- the projection is handed its own",
        "phases": phases,
        "overall_assessment": {"structural_presence_score": 84.0},
        "recommendations": ["Finish Phase 2"],
    }
    results.update(policy.overall([(score, weight) for _name, score, weight in scored]))
    return results


def _empty_phase_skeleton(phase_name: str) -> Dict[str, Any]:
    """``_empty_phase_result``'s literal, evaluated out of the heavy module.

    Read as data rather than imported, for the reason in the module docstring.
    Evaluating the producer's own literal is what makes the fixture able to
    catch a key seeded there -- a hand-copied skeleton would not.
    """
    function = next(
        node
        for node in ast.walk(_system_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_empty_phase_result"
    )
    returned = next(stmt for stmt in ast.walk(function) if isinstance(stmt, ast.Return))
    skeleton: Dict[str, Any] = {}
    for key, value in zip(returned.value.keys, returned.value.values):
        name = ast.literal_eval(key)
        try:
            skeleton[name] = ast.literal_eval(value)
        except ValueError:
            # `validations` is a comprehension over a name defined above; its
            # content does not matter to the report contract.
            skeleton[name] = {}
    skeleton["phase_name"] = phase_name
    return skeleton


def _non_comment_lines(text: str) -> list[str]:
    """Workflow lines that are not comments.

    Comments explaining a removed construct quote it verbatim, so a scanner
    that reads a quotation as an occurrence is measuring the prose. That was a
    real finding on this very file's first guard, not a hypothetical.

    Delegates to the canonical stripper (#17941): a private copy here would be
    the thirty-second, and the guard that counts them is right to refuse it.
    """
    return [cl.text for cl in code_lines(text, name="x.sh")]


def _logical_lines(text: str) -> list[str]:
    """Non-comment lines with backslash continuations joined into one line.

    A shell command split over continuations is one command, and the pieces a
    guard cares about land on different physical lines: the validator call is
    on one, its redirect on the next. A per-physical-line scan for `|| true`
    therefore inspects the line naming the script and never sees an operator
    appended after the redirect -- which is exactly where it would go. Joining
    first makes the guard read the command the shell runs.

    `code_lines(join_continuations=True)` is both halves, so neither is
    re-derived here (#17941, #16414).
    """
    return [cl.text for cl in code_lines(text, name="x.sh", join_continuations=True)]


def _keys_the_workflow_reads() -> set[str]:
    """Top-level report keys the workflow consumes, read out of its source.

    Three shapes, because the workflow reads the artifact three ways: the
    gate steps shell out to ``phase_report_figure.py <report> <key>``, the
    summary steps use ``r.get("key")`` in an inline Python reader, and the PR
    comment is JavaScript reading ``results.key``.
    """
    text = _workflow_text()
    keys: set[str] = set()
    keys.update(re.findall(rf"{re.escape(_READER.name)}\s*\\?\s*\n?\s*{re.escape(_REPORT_FILE)}\s+([a-z_]+)", text))
    keys.update(re.findall(r"""\br\.get\(["']([a-z_]+)["']""", text))
    keys.update(re.findall(r"\bresults\.([a-z_]+)\b", text))
    return keys


class TestNothingTheWorkflowReadsIsMissing:
    """The producer/consumer key lists are compared, never both hand-kept."""

    def test_the_scan_found_the_keys(self) -> None:
        keys = _keys_the_workflow_reads()
        assert len(keys) >= _MIN_KEYS_READ, (
            f"the workflow scan found only {sorted(keys)} -- fewer than the {_MIN_KEYS_READ} known reads, "
            "so the regexes no longer match the file and this guard is checking nothing"
        )
        assert "structural_presence" in keys, "the gate's own key vanished from the workflow -- scan is broken"

    def test_every_key_the_workflow_reads_is_in_the_projection(self) -> None:
        report = _policy().project_report(_ci_mode_results(), _STAMP)
        missing = sorted(_keys_the_workflow_reads() - set(report))
        assert not missing, (
            "the workflow reads these top-level keys and the report does not carry them, so each one "
            f"reaches its consumer as None: {missing}. Present in the report: {sorted(report)}"
        )

    def test_structural_presence_survives_the_projection_as_a_number(self) -> None:
        # The #17674 regression itself, stated as the gate states it.
        report = _policy().project_report(_ci_mode_results(), _STAMP)
        value = report.get("structural_presence")
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"structural_presence is {value!r} in the projected report; the CI gate reads exactly this key "
            "and renders a non-number as 0, which then fails the 60% threshold"
        )

    def test_a_key_added_to_the_aggregate_reaches_the_artifact(self) -> None:
        # The CLASS, not the instance: a hand-written whitelist passes the test
        # above the moment someone adds the one missing key, and drops the next
        # one exactly as before.
        results = _ci_mode_results()
        results["a_figure_nobody_has_added_yet"] = 42
        report = _policy().project_report(results, _STAMP)
        assert report.get("a_figure_nobody_has_added_yet") == 42, (
            "a new top-level key did not survive the projection -- it is still an enumerated whitelist, "
            "which is the mechanism that dropped structural_presence (#17674)"
        )

    def test_the_restructured_keys_are_still_rebuilt_and_not_copied(self) -> None:
        report = _policy().project_report(_ci_mode_results(), _STAMP)
        assert isinstance(report["phases"], list), "phases must be projected to a list, not copied as the dict"
        assert [p["name"] for p in report["phases"]] == [
            "Phase 1: Core Infrastructure",
            "Phase 2: Knowledge Base and Memory",
            "Phase 6: Enhanced UI/UX",
        ]
        assert report["recommendations"] == [{"title": "Finish Phase 2", "action": "Review and implement"}]
        assert report["timestamp"] == _STAMP

    def test_a_deferring_phase_reports_no_percentage_rather_than_zero(self) -> None:
        # The fixture's phase dicts come from `_empty_phase_result` + the real
        # `as_report()`, so this reads the producer, not a literal. It failed
        # against `main`, where `_empty_phase_result` seeded a 0 that
        # `as_report()` never overrides for a deferring phase -- the live
        # artifact shipped "Phase 6: Enhanced UI/UX: 0.0% structural presence".
        report = _policy().project_report(_ci_mode_results(), _STAMP)
        deferred = next(p for p in report["phases"] if p["name"] == "Phase 6: Enhanced UI/UX")
        assert (
            deferred["structural_presence_percentage"] is None
        ), "a phase verified by dedicated gates must report None, not 0 -- 0 reads as measured and empty"

    def test_the_deliberately_dropped_keys_are_declared_and_absent(self) -> None:
        policy = _policy()
        report = policy.project_report(_ci_mode_results(), _STAMP)
        # Named, not just iterated: emptying DROPPED_KEYS would make a bare
        # loop pass having checked nothing, which is the vacuity failure this
        # file exists to prevent. The drop must stay DECLARED, because a key
        # that disappears from the artifact for no recorded reason is the
        # silent-drop class this issue is about.
        assert "overall_assessment" in policy.DROPPED_KEYS, (
            "overall_assessment is no longer declared in DROPPED_KEYS. Either carry it through, or "
            "re-declare the drop with its reason -- an undeclared omission is the #17674 class"
        )
        for key, reason in policy.DROPPED_KEYS.items():
            assert key not in report, f"{key} is declared dropped ({reason}) but reached the artifact"
            assert reason, f"{key} is dropped with no stated reason"
        assert not (policy.REBUILT_KEYS & set(policy.DROPPED_KEYS)), "a key cannot be both rebuilt and dropped"

    def test_nothing_weighable_is_not_a_zero(self) -> None:
        # Every phase deferring means no denominator, not a 0% repo. A 0.0 here
        # is a number the gate's reader would accept and fail on.
        policy = _policy()
        aggregate = policy.overall([(policy.PhaseScore(ran=0, passed=0, defers_to=("x.yml",)), 50.0)])
        assert aggregate["structural_presence"] is None
        assert aggregate["overall_maturity"] is None
        assert "could be weighed" in aggregate["measures"]


class TestAnAbsentFigureIsNotAZero:
    """``phase_report_figure`` separates four facts the old gate merged into ``0``."""

    def _write(self, tmp_path: Path, payload: str) -> str:
        path = tmp_path / _REPORT_FILE
        path.write_text(payload, encoding="utf-8")
        return str(path)

    def test_a_real_zero_is_returned_and_not_rejected(self, tmp_path: Path) -> None:
        # The discriminating case. A guard that only rejects falsy values has
        # swapped one indistinguishable pair for another.
        path = self._write(tmp_path, json.dumps({"structural_presence": 0.0, "measures": "structural presence only"}))
        assert _reader().read_figure(path, "structural_presence") == 0.0

    def test_an_absent_key_names_the_keys_that_are_present(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, json.dumps({"overall_maturity": None, "measures": "nothing ran"}))
        reader = _reader()
        with pytest.raises(reader.NoMeasurement) as excinfo:
            reader.read_figure(path, "structural_presence")
        message = str(excinfo.value)
        assert "structural_presence" in message, "the error must name the key that was asked for"
        assert (
            "overall_maturity" in message and "measures" in message
        ), f"the error must list the keys actually found, so the next mismatch is diagnosable from the log: {message}"
        assert "NOT a low score" in message

    def test_a_null_value_is_not_a_measurement(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, json.dumps({"structural_presence": None}))
        reader = _reader()
        with pytest.raises(reader.NoMeasurement):
            reader.read_figure(path, "structural_presence")

    def test_a_boolean_is_not_a_measurement(self, tmp_path: Path) -> None:
        # ``True`` is an ``int`` in Python and would otherwise gate as 1%.
        path = self._write(tmp_path, json.dumps({"structural_presence": True}))
        reader = _reader()
        with pytest.raises(reader.NoMeasurement):
            reader.read_figure(path, "structural_presence")

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_a_non_finite_float_is_not_a_measurement(self, tmp_path: Path, literal: str) -> None:
        # `json` round-trips these happily and `bc` reads them as 0, so they
        # are number-shaped non-measurements -- this issue in another costume.
        path = self._write(tmp_path, '{"structural_presence": %s}' % literal)
        reader = _reader()
        with pytest.raises(reader.NoMeasurement):
            reader.read_figure(path, "structural_presence")

    def test_a_missing_file_says_unreadable_and_not_zero(self, tmp_path: Path) -> None:
        reader = _reader()
        with pytest.raises(reader.NoMeasurement) as excinfo:
            reader.read_figure(str(tmp_path / "absent.json"), "structural_presence")
        assert "unreadable" in str(excinfo.value)

    def test_unparseable_json_says_so(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "{not json")
        reader = _reader()
        with pytest.raises(reader.NoMeasurement) as excinfo:
            reader.read_figure(path, "structural_presence")
        assert "not valid JSON" in str(excinfo.value)

    def test_main_exits_non_zero_and_prints_no_number(self, tmp_path: Path, capsys) -> None:
        reader = _reader()
        path = self._write(tmp_path, json.dumps({"measures": "nothing ran"}))
        assert reader.main([path, "structural_presence"]) == reader.NO_MEASUREMENT
        captured = capsys.readouterr()
        assert captured.out.strip() == "", f"a failed read printed {captured.out!r} to stdout -- a gate would parse it"
        assert "::error::" in captured.err

    def test_main_prints_the_figure_on_success(self, tmp_path: Path, capsys) -> None:
        reader = _reader()
        path = self._write(tmp_path, json.dumps({"structural_presence": 93.5}))
        assert reader.main([path, "structural_presence"]) == 0
        assert capsys.readouterr().out.strip() == "93.5"


class TestNoGateFabricatesANumber:
    """The workflow may not re-create the default this issue removed."""

    def test_every_gate_assignment_reads_through_the_shared_reader(self) -> None:
        # NOT a count of occurrences: the first version of this test counted
        # every line containing the reader's name, and one of those lines was
        # the COMMENT explaining the reader. Gate 2 could have reverted to an
        # inline one-liner with the count still reading 2. What has to hold is
        # that each `MATURITY=$(...)` assignment calls the reader, so that is
        # what is asserted, over non-comment lines only.
        assignments = [
            line.strip() for line in _non_comment_lines(_workflow_text()) if re.search(r"^\s*MATURITY=\$\(", line)
        ]
        assert len(assignments) == 2, (
            f"expected the two gate assignments, found {len(assignments)}: {assignments}. "
            "A new gate must read through the shared reader, and a removed one must update this guard"
        )
        inline = [line for line in assignments if _READER.name not in line]
        assert not inline, (
            f"these gate assignments do not call {_READER.name}, so they re-create the "
            f"absent-reads-as-zero path in their own copy: {inline}"
        )

    @pytest.mark.parametrize(
        "pattern",
        [
            r"""\|\|\s*echo\s*["']0["']""",
            r"""get\(["'](?:structural_presence|overall_maturity)["']\s*,\s*0\)""",
            r"""print\(v if isinstance""",
        ],
    )
    def test_the_zero_default_is_gone(self, pattern: str) -> None:
        # Comment lines are excluded deliberately: the comments explaining what
        # was removed quote the removed code verbatim, and a scanner that reads
        # a quotation as an occurrence is measuring the prose.
        hits = [line.strip() for line in _non_comment_lines(_workflow_text()) if re.search(pattern, line)]
        assert not hits, f"a zero-default for an unread figure is back in the workflow: {hits}"

    def test_the_nothing_ran_fallback_does_not_claim_a_zero(self) -> None:
        text = _workflow_text()
        assert '"structural_presence": 0,' not in text, (
            "the no-valid-JSON fallback writes structural_presence: 0, which makes a broken instrument "
            "indistinguishable from a repo that scores 0%"
        )
        assert '"structural_presence": null' in text


class TestTheProducerIsActuallyWiredToTheProjection:
    """The regression is the WIRING, and the rest of this file does not test it.

    Every other test here calls ``phase_score.project_report`` directly. That
    proves the helper is correct and proves nothing about ``_output_json_results``,
    which is the function that was wrong -- reverting it to the hand-written
    four-key dict leaves all of them green while the artifact loses
    ``structural_presence`` again. ``phase_validation_system`` cannot be
    imported here (see the module docstring), so the call is asserted as data.
    """

    @staticmethod
    def _output_json_results() -> ast.AST:
        return next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_output_json_results"
        )

    def test_it_calls_project_report(self) -> None:
        called = {
            node.func.id
            for node in ast.walk(self._output_json_results())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "project_report" in called, (
            "_output_json_results does not call project_report, so the artifact is built by something "
            "other than the shared projection -- which is exactly the #17674 regression"
        )

    def test_it_builds_no_report_dict_of_its_own(self) -> None:
        # The specific shape that broke: a dict literal enumerating the
        # top-level report keys by hand.
        literals = [
            sorted(ast.literal_eval(key) for key in node.keys if isinstance(key, ast.Constant))
            for node in ast.walk(self._output_json_results())
            if isinstance(node, ast.Dict)
        ]
        offending = [keys for keys in literals if {"overall_maturity", "structural_presence"} & set(keys)]
        assert not offending, (
            "_output_json_results builds its own dict of top-level report keys again: "
            f"{offending}. That hand-written whitelist is what dropped structural_presence"
        )

    def test_project_report_is_imported_from_the_policy_module(self) -> None:
        imported = {
            alias.name
            for node in ast.walk(_system_tree())
            if isinstance(node, ast.ImportFrom) and node.module == "phase_score"
            for alias in node.names
        }
        assert "project_report" in imported, "project_report is not imported from phase_score"


class TestTheProducerDoesNotCrashOnAnUnmeasuredFigure:
    """``None < 50`` ran on every CI run, after the report was already written."""

    @staticmethod
    def _function(name: str) -> ast.AST:
        return next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        )

    @pytest.mark.parametrize("name", ["main", "_output_summary_results"])
    def test_overall_maturity_is_not_read_with_a_zero_default(self, name: str) -> None:
        # `.get("overall_maturity", 0)` cannot fire its default: the key is
        # PRESENT and null whenever a group was skipped. It reads as a safe
        # idiom and is the bug.
        source = ast.unparse(self._function(name))
        assert "'overall_maturity', 0" not in source and '"overall_maturity", 0' not in source, (
            f"{name} still defaults overall_maturity to 0. The key is present and None in --ci-mode, "
            "so the default never fires and the None reaches a comparison or a format spec"
        )

    @pytest.mark.parametrize("name", ["main", "_output_summary_results"])
    def test_a_none_maturity_is_handled_before_it_is_used(self, name: str) -> None:
        source = ast.unparse(self._function(name))
        assert "maturity is None" in source, (
            f"{name} does not test `maturity is None` before using it; `None < 50` raises TypeError and "
            "`'%.1f' % None` raises, both AFTER a correct report has been written"
        )

    def test_the_not_measured_exit_code_is_distinct(self) -> None:
        constants = {
            target.id: ast.literal_eval(node.value)
            for node in ast.walk(_system_tree())
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert constants.get("EXIT_NOT_MEASURED") not in (0, 1, 2, 3), (
            "EXIT_NOT_MEASURED must not collide with a measured verdict (0/1/2) or with a failed "
            f"run (3); it is {constants.get('EXIT_NOT_MEASURED')!r}"
        )


class TestTheEmptySkeletonSeedsNoFigure:
    """#17674: the 0 that survived `as_report()` for a deferring phase."""

    def test_empty_phase_result_does_not_seed_a_percentage(self) -> None:
        assert "structural_presence_percentage" not in _empty_phase_skeleton("Phase 6: Enhanced UI/UX"), (
            "_empty_phase_result seeds structural_presence_percentage. A deferring phase's as_report() "
            "omits the key, so the seed survives and the artifact reports 0.0% for a phase that "
            "reports no figure by design"
        )

    def test_a_non_deferring_phase_still_gets_one(self) -> None:
        # The seed's removal must not leave an ordinary phase without a figure.
        phase = _empty_phase_skeleton("Phase 1: Core Infrastructure")
        phase.update(_policy().PhaseScore(ran=4, passed=3, skipped=("endpoints",)).as_report())
        assert phase["structural_presence_percentage"] == 75.0


class TestTheValidatorExitCodeIsNotSwallowed:
    """A blanket `|| true` is the same absent-reads-as-fine failure, in bash."""

    def test_the_run_step_reports_the_exit_code(self) -> None:
        lines = _logical_lines(_workflow_text())
        invocation = [line for line in lines if "phase_validation_system.py" in line and "python" in line]
        assert invocation, "the validator invocation vanished from the workflow"
        swallowed = [line for line in invocation if "|| true" in line or "|| :" in line]
        assert not swallowed, (
            f"the validator's exit code is swallowed: {swallowed}. A crash and a clean "
            "run then produce the same silence"
        )
        assert any(
            "VALIDATOR_RC" in line for line in lines
        ), "the validator's exit code is neither reported nor acted on; capture it and echo it"
