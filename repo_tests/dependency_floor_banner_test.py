# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The below-floor banner must reach the terminal, and only when it has something to say (#15091).

The plugin's whole value is that it prints next to a green result. A version of
it that is written but not registered, or that renders without naming the two
versions, is indistinguishable from the silence this issue exists to end -- so
the registration and the rendered text are both asserted here, not assumed.
"""

from __future__ import annotations

import pathlib

import pytest
from repo_tests import dependency_floor_banner as banner

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _FakeReporter:
    """Minimal stand-in for pytest's TerminalReporter."""

    def __init__(self):
        self.separators: list[tuple[str, str]] = []
        self.lines: list[str] = []

    def write_sep(self, char, title, **_kwargs):
        self.separators.append((char, title))

    def write_line(self, line, **_kwargs):
        self.lines.append(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _shortfall(checker, name="fastapi", installed="0.135.2", required="0.141.1"):
    declaration = checker.Declaration(
        source="autobot-backend/requirements.txt:7", name=name, operator=">=", required=required
    )
    return checker.Shortfall(declaration, installed)


class TestRegistration:
    def test_the_rootdir_conftest_actually_loads_the_plugin(self):
        """A plugin nobody registers prints nothing, which is the status quo."""
        conftest = (REPO_ROOT / "conftest.py").read_text(encoding="utf-8")
        assert "repo_tests.dependency_floor_banner" in conftest

    def test_the_checker_it_delegates_to_exists(self):
        assert banner._CHECKER.is_file(), f"missing checker at {banner._CHECKER}"

    def test_loading_the_checker_yields_the_audit_api(self):
        checker = banner._load_checker()
        assert callable(checker.audit)
        assert callable(checker.render)

    def test_loading_registers_the_module_and_reuses_it(self):
        """@dataclass needs the sys.modules key; a second load must not re-execute."""
        import sys

        first = banner._load_checker()
        assert sys.modules.get(banner._MODULE_NAME) is first
        assert banner._load_checker() is first


class TestTerminalSummary:
    def test_silent_when_every_floor_is_satisfied(self, monkeypatch):
        checker = banner._load_checker()
        monkeypatch.setattr(banner, "_load_checker", lambda: checker)
        monkeypatch.setattr(checker, "audit", lambda root: ([], 206))
        reporter = _FakeReporter()
        banner.pytest_terminal_summary(reporter)
        assert reporter.lines == []
        assert reporter.separators == []

    def test_names_both_versions_when_below_floor(self, monkeypatch):
        checker = banner._load_checker()
        monkeypatch.setattr(banner, "_load_checker", lambda: checker)
        monkeypatch.setattr(checker, "audit", lambda root: ([_shortfall(checker)], 206))
        reporter = _FakeReporter()
        banner.pytest_terminal_summary(reporter)
        assert reporter.separators, "the banner must be visually separated from the counts"
        assert "0.135.2" in reporter.text
        assert "0.141.1" in reporter.text
        assert "fastapi" in reporter.text

    def test_points_at_the_remedy(self, monkeypatch):
        checker = banner._load_checker()
        monkeypatch.setattr(banner, "_load_checker", lambda: checker)
        monkeypatch.setattr(checker, "audit", lambda root: ([_shortfall(checker)], 206))
        reporter = _FakeReporter()
        banner.pytest_terminal_summary(reporter)
        assert "scripts/setup-ci-parity-env.sh" in reporter.text

    def test_an_empty_enumeration_propagates_instead_of_printing_all_clear(self, monkeypatch):
        """#15087 discipline: the banner must never render silence from no data."""
        checker = banner._load_checker()

        def _raise(_root):
            raise checker.EmptyEnumerationError("no version declarations found")

        monkeypatch.setattr(banner, "_load_checker", lambda: checker)
        monkeypatch.setattr(checker, "audit", _raise)
        with pytest.raises(checker.EmptyEnumerationError):
            banner.pytest_terminal_summary(_FakeReporter())


class TestAgainstTheRealTree:
    def test_the_repo_enumerates_a_substantial_declaration_set(self):
        """Guards the enumeration itself: a silent drop to zero would hide everything."""
        checker = banner._load_checker()
        _found, examined = checker.audit(REPO_ROOT)
        assert examined > 100, f"only {examined} declarations enumerated across the repo"
