# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pipeline-scripts/dependency_floor_report.py (#17558).

Split from check_dependency_floors_test.py when that file reached the 600-line
ceiling. The seam follows the module split it tests: `render` and `FloorAudit`
moved to their own module because reporting is where #17558's defect lived, and
their tests belong beside them rather than beside the measurement code.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_CHECKER = pathlib.Path(__file__).resolve().parent / "check_dependency_floors.py"
_spec = importlib.util.spec_from_file_location("check_dependency_floors", _CHECKER)
checker = importlib.util.module_from_spec(_spec)
sys.modules["check_dependency_floors"] = checker
try:
    _spec.loader.exec_module(checker)
finally:
    # Installed only for the duration of exec_module -- a dataclass defined in
    # the module resolves its own module by name while the body runs. Left
    # installed, it puts a `pipeline-scripts/` module into the sys.modules of
    # every test that runs after this one, which is what the leak guard reports
    # and what it exists to stop. The `checker` reference below stays valid;
    # only the global registry entry goes.
    sys.modules.pop("check_dependency_floors", None)


def _declaration(name: str = "fastapi", required: str = "0.141.1"):
    return checker.Declaration(source="autobot-backend/requirements.txt:1", name=name, operator=">=", required=required)


def _result(found, declared=206, *, compared=None, not_installed=(), roots=("req.txt",), environment=None):
    """A :class:`FloorAudit` for render tests (#17558 changed render's input).

    ``compared`` defaults to ``declared`` so existing expectations about the
    number in the first line stay meaningful; the tests that care about the
    distinction set it explicitly.
    """
    return checker.FloorAudit(
        shortfalls=tuple(found),
        declared=declared,
        compared=declared if compared is None else compared,
        not_installed=tuple(not_installed),
        not_compared_declarations=len(not_installed),
        roots=tuple(roots),
        environment=environment
        or f"the interpreter running this check (python {__import__('platform').python_version()})",
    )


class TestRender:
    def test_names_both_versions_and_the_remedy(self):
        """The acceptance criterion: the report must name installed AND declared."""
        report = "\n".join(checker.render(_result([checker.Shortfall(_declaration(), "0.135.2")])))
        assert "0.135.2" in report
        assert "0.141.1" in report
        assert "fastapi" in report
        assert "scripts/setup-ci-parity-env.sh" in report

    def test_clean_environment_says_how_many_were_checked(self):
        """#17558: and says how many it could NOT check, and against what."""
        report = "\n".join(checker.render(_result([], declared=206, compared=206)))
        assert "206" in report and "all satisfied" in report
        assert "roots:" in report, "a clean verdict must name the declarations it compared against"
        assert "report only" in report, "a block that cannot fail the run must say so"

    def test_a_clean_pass_counts_comparisons_and_admits_what_it_skipped(self):
        """The defect this issue exists for: 128 declared, 42 never compared.

        The old line said "206 declarations checked, all satisfied" whether or
        not anything was installed to compare them against.
        """
        report = "\n".join(
            checker.render(_result([], declared=128, compared=86, not_installed=tuple(f"p{i}" for i in range(42))))
        )
        assert "86 of 128" in report, "the pass must count comparisons, not declarations read"
        # #17610 review changed the wording to name both units: declarations not
        # compared, and the distinct packages behind them. The old string counted
        # packages while reading as declarations.
        assert "42 declaration(s) not compared" in report
        assert "42 distinct package(s) not installed" in report

    def test_detail_is_capped_and_the_remainder_counted(self):
        found = [checker.Shortfall(_declaration(name=f"pkg{i}"), "0.1") for i in range(25)]
        report = "\n".join(checker.render(_result(found), limit=10))
        assert "pkg0" in report
        assert "pkg24" not in report
        assert "15 more" in report

    def test_default_points_at_ci_as_a_different_environment(self):
        """#16264: off CI, the report describes some OTHER interpreter than CI's."""
        report = "\n".join(checker.render(_result([checker.Shortfall(_declaration(), "0.135.2")])))
        assert "carries no information about CI" in report
        assert "CI job's own environment" not in report

    def test_in_ci_names_the_running_environment_as_ci_itself(self):
        """#16264: printed FROM CI, the interpreter making the report IS CI's own."""
        report = "\n".join(checker.render(_result([checker.Shortfall(_declaration(), "0.135.2")]), in_ci=True))
        assert "CI job's own environment" in report
        assert "carries no information about CI" not in report


class TestTheReportNamesItsEnvironment:
    """A number without its environment is what caused two retractions in one day."""

    def _one(self):
        return [
            checker.Shortfall(
                checker.Declaration(source="req.txt:1", name="pkg", operator=">=", required="2.0"),
                "1.0",
            )
        ]

    def test_the_default_still_names_the_running_interpreter(self):
        assert "interpreter running this check" in checker.render(_result(self._one(), declared=1))[0]

    def test_a_named_environment_replaces_it(self):
        line = checker.render(
            _result(self._one(), declared=1, environment="/opt/x/venv/bin/python (python 3.14.6)"), deployed=True
        )[0]
        assert "/opt/x/venv/bin/python (python 3.14.6)" in line
        assert "interpreter running this check" not in line

    def test_a_deployed_report_does_not_give_ci_parity_advice(self):
        lines = checker.render(_result(self._one(), declared=1, environment="/opt/x/venv/bin/python"), deployed=True)
        assert not any("setup-ci-parity-env.sh" in line for line in lines)
        assert any("DEPLOYED environment" in line for line in lines)
