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

    Built from the REAL ``PhaseScore``/``overall`` policy rather than from a
    literal dict: a hand-written fixture would pin whatever the test author
    believed the aggregate emits, which is the same mistake as a hand-written
    projection. Every phase carries a skipped live-stack group, because
    ``--ci-mode`` brings no stack up -- which is what makes ``overall_maturity``
    null and ``structural_presence`` the only figure a gate can read.
    """
    policy = _policy()
    scores = [
        (policy.PhaseScore(ran=4, passed=4, skipped=("endpoints", "services")), 100.0),
        (policy.PhaseScore(ran=3, passed=2, skipped=("ui_features",)), 60.0),
        (policy.PhaseScore(ran=0, passed=0, defers_to=("frontend-quality.yml",)), 80.0),
    ]
    results: Dict[str, Any] = {
        "timestamp": "ignored -- the projection is handed its own",
        "phases": {
            "Phase 1: Core Infrastructure": {
                "status": "structural-presence-only",
                "structural_presence_percentage": 100.0,
                "complete": False,
                "not_checked": {"endpoints": policy.NOT_CHECKED},
                "validations": {"files": {"passed": 4, "total": 4}},
            },
            "Phase 6: Enhanced UI/UX": {
                "status": "deferred-to-dedicated-gates",
                "complete": False,
                "authoritative_gates": ["frontend-quality.yml"],
            },
        },
        "overall_assessment": {"structural_presence_score": 84.0},
        "recommendations": ["Finish Phase 2"],
    }
    results.update(policy.overall(scores))
    return results


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
            "Phase 6: Enhanced UI/UX",
        ]
        assert report["recommendations"] == [{"title": "Finish Phase 2", "action": "Review and implement"}]
        assert report["timestamp"] == _STAMP

    def test_a_deferring_phase_reports_no_percentage_rather_than_zero(self) -> None:
        report = _policy().project_report(_ci_mode_results(), _STAMP)
        deferred = next(p for p in report["phases"] if p["name"] == "Phase 6: Enhanced UI/UX")
        assert (
            deferred["structural_presence_percentage"] is None
        ), "a phase verified by dedicated gates must report None, not 0 -- 0 reads as measured and empty"


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

    def test_both_gates_read_through_the_shared_reader(self) -> None:
        text = _workflow_text()
        uses = text.count(_READER.name)
        assert uses >= 2, (
            f"{_READER.name} is referenced {uses} time(s); both the phase gate and the integration gate "
            "must read through it, or the next fix lands in only one of them"
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
        hits = [
            line.strip()
            for line in _workflow_text().splitlines()
            if not line.lstrip().startswith(("#", "//")) and re.search(pattern, line)
        ]
        assert not hits, f"a zero-default for an unread figure is back in the workflow: {hits}"

    def test_the_nothing_ran_fallback_does_not_claim_a_zero(self) -> None:
        text = _workflow_text()
        assert '"structural_presence": 0,' not in text, (
            "the no-valid-JSON fallback writes structural_presence: 0, which makes a broken instrument "
            "indistinguishable from a repo that scores 0%"
        )
        assert '"structural_presence": null' in text


class TestEveryDeclaredFeatureHasAValidator:
    """#17559: a feature with no validator used to report implemented."""

    @staticmethod
    def _criteria_block() -> ast.Dict:
        return next(
            stmt.value
            for node in ast.walk(_system_tree())
            if isinstance(node, ast.ClassDef)
            for stmt in node.body
            if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "PHASE_CRITERIA" for t in stmt.targets)
        )

    @classmethod
    def _declared_features(cls) -> set[str]:
        found: set[str] = set()
        for criteria in cls._criteria_block().values:
            for key, value in zip(criteria.keys, criteria.values):
                # `performance_metrics` is a dict of thresholds handled by its
                # own validator, not a list of feature names.
                if ast.literal_eval(key).endswith("_features"):
                    found.update(ast.literal_eval(element) for element in value.elts)
        return found

    @staticmethod
    def _validator_names() -> set[str]:
        function = next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_get_feature_validators"
        )
        returned = next(stmt for stmt in ast.walk(function) if isinstance(stmt, ast.Return))
        return {ast.literal_eval(key) for key in returned.value.keys}

    def test_the_parse_found_both_sides(self) -> None:
        assert len(self._declared_features()) >= 20, "the criteria parse collapsed -- this guard would pass vacuously"
        assert len(self._validator_names()) >= 20, "the validator-map parse collapsed"

    def test_no_declared_feature_is_unvalidated(self) -> None:
        missing = sorted(self._declared_features() - self._validator_names())
        assert not missing, (
            "these features are declared in PHASE_CRITERIA with no entry in _get_feature_validators(), so "
            f"nothing checks them: {missing}. Give each one a validator, or remove the claim (#17559)"
        )

    def test_an_unvalidated_feature_is_not_reported_implemented(self) -> None:
        # Read as data rather than imported: see the module docstring.
        function = next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_validate_single_feature"
        )
        returned = [
            stmt.value.value
            for stmt in ast.walk(function)
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant)
        ]
        assert returned, "no literal return found in _validate_single_feature -- the parse missed the fallback"
        assert True not in returned, (
            "_validate_single_feature returns a literal True. A feature nobody wrote a check for would "
            "then be indistinguishable from one that was checked and found present (#17559)"
        )
