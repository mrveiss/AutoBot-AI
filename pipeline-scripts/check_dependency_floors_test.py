# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the declared-dependency-floor reporter (#15091).

Every case builds its own requirement tree and supplies its own installed-version
mapping. Nothing here reads the ambient interpreter: a test that asserted against
the real environment would pass on a box that is below floor and fail on one that
is not, which is the exact defect the subject exists to report.
"""

from __future__ import annotations

import check_dependency_floors as checker
import pytest


def _write(root, relative, body):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _declaration(name="fastapi", operator=">=", required="0.141.1", source="r.txt:1"):
    return checker.Declaration(source=source, name=name, operator=operator, required=required)


class TestSatisfies:
    @pytest.mark.parametrize(
        "installed,operator,required,expected",
        [
            ("0.141.1", ">=", "0.141.1", True),
            ("0.141.2", ">=", "0.141.1", True),
            ("0.135.2", ">=", "0.141.1", False),
            # 0.9 vs 0.10 is the comparison a string sort gets backwards.
            ("0.9.0", ">=", "0.10.0", False),
            # Unequal segment counts must pad, not rank by length.
            ("1.6", ">=", "1.6.0", True),
            ("1.6.0", ">=", "1.6", True),
            ("1.6.1", ">=", "1.6", True),
            # A pre-release is below the release it precedes.
            ("1.6.0rc1", ">=", "1.6.0", False),
            ("1.6.0", ">=", "1.6.0rc1", True),
            ("0.141.1", "==", "0.141.1", True),
            ("0.141.2", "==", "0.141.1", False),
            ("0.141.1", ">", "0.141.1", False),
            ("0.141.2", ">", "0.141.1", True),
            ("2.1.3", "~=", "2.1.0", True),
        ],
    )
    def test_ordering(self, installed, operator, required, expected):
        assert checker.satisfies(installed, operator, required) is expected

    def test_unparsable_installed_version_is_reported_not_accepted(self):
        """An unreadable version must not be allowed to pass as satisfying."""
        assert checker.satisfies("not-a-version", ">=", "1.0.0") is False


class TestCanonicalName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Case folding alone -- PEP 503 introduces no separator.
            ("PyJWT", "pyjwt"),
            ("pyjwt", "pyjwt"),
            # Every separator spelling collapses to a single hyphen.
            ("Py_JWT", "py-jwt"),
            ("py.jwt", "py-jwt"),
            ("PY-JWT", "py-jwt"),
            ("typing_extensions", "typing-extensions"),
            ("ruamel.yaml", "ruamel-yaml"),
            ("a__b", "a-b"),
        ],
    )
    def test_folds_to_one_key(self, raw, expected):
        assert checker.canonical(raw) == expected


class TestParseDeclarations:
    def test_captures_name_operator_version_and_position(self, tmp_path):
        path = _write(tmp_path, "requirements.txt", "# a comment\n\nfastapi>=0.141.1  # SECURITY\n")
        [declaration] = checker.parse_declarations([path], tmp_path)
        assert declaration.name == "fastapi"
        assert declaration.operator == ">="
        assert declaration.required == "0.141.1"
        assert declaration.source == "requirements.txt:3"

    def test_include_and_option_lines_are_not_requirements(self, tmp_path):
        path = _write(tmp_path, "r.txt", "-r other.txt\n--index-url https://example.invalid\n-e ./pkg\n")
        assert checker.parse_declarations([path], tmp_path) == []

    def test_first_specifier_of_a_capped_range_is_the_floor(self, tmp_path):
        path = _write(tmp_path, "r.txt", "websockets>=15.0.1,<16\n")
        [declaration] = checker.parse_declarations([path], tmp_path)
        assert (declaration.operator, declaration.required) == (">=", "15.0.1")

    def test_extras_do_not_break_the_name(self, tmp_path):
        path = _write(tmp_path, "r.txt", "uvicorn[standard]>=0.52.4\n")
        [declaration] = checker.parse_declarations([path], tmp_path)
        assert declaration.name == "uvicorn"


class TestDeclarationFiles:
    def test_follows_include_graph_transitively(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("top.txt",))
        _write(tmp_path, "top.txt", "-r nested/mid.txt\n")
        _write(tmp_path, "nested/mid.txt", "--requirement leaf.txt\n")
        _write(tmp_path, "nested/leaf.txt", "fastapi>=0.141.1\n")
        names = [path.name for path in checker.declaration_files(tmp_path)]
        assert names == ["top.txt", "mid.txt", "leaf.txt"]

    def test_absent_root_is_skipped_without_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("gone.txt", "here.txt"))
        _write(tmp_path, "here.txt", "fastapi>=0.141.1\n")
        assert [path.name for path in checker.declaration_files(tmp_path)] == ["here.txt"]

    def test_include_cycle_terminates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("a.txt",))
        _write(tmp_path, "a.txt", "-r b.txt\n")
        _write(tmp_path, "b.txt", "-r a.txt\n")
        assert [path.name for path in checker.declaration_files(tmp_path)] == ["a.txt", "b.txt"]


class TestShortfalls:
    def test_below_floor_is_reported_with_the_installed_version(self):
        declaration = _declaration()
        [shortfall] = checker.shortfalls([declaration], {"fastapi": "0.135.2"})
        assert shortfall.installed == "0.135.2"
        assert shortfall.declaration is declaration

    def test_at_or_above_floor_is_silent(self):
        assert checker.shortfalls([_declaration()], {"fastapi": "0.141.1"}) == []

    def test_absent_distribution_is_not_a_shortfall(self):
        """Not installed says nothing about the version CI would resolve."""
        assert checker.shortfalls([_declaration()], {}) == []


class TestAuditRefusesAnEmptyEnumeration:
    def test_empty_tree_raises_instead_of_reporting_clean(self, tmp_path, monkeypatch):
        """#15087: a check that asserts over an enumeration must fail when it is empty.

        Reporting "0 declarations checked, all satisfied" from a tree with no
        requirements files is indistinguishable from a healthy environment, and
        would make every caller silently stop checking.
        """
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("absent.txt",))
        with pytest.raises(checker.EmptyEnumerationError):
            checker.audit(tmp_path)

    def test_requirement_files_that_declare_nothing_also_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        _write(tmp_path, "r.txt", "# nothing but a comment\n")
        with pytest.raises(checker.EmptyEnumerationError):
            checker.audit(tmp_path)

    def test_a_populated_tree_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        _write(tmp_path, "r.txt", "fastapi>=0.141.1\n")
        found, examined = checker.audit(tmp_path)
        assert examined == 1
        assert isinstance(found, list)


class TestRender:
    def test_names_both_versions_and_the_remedy(self):
        """The acceptance criterion: the report must name installed AND declared."""
        report = "\n".join(checker.render([checker.Shortfall(_declaration(), "0.135.2")], 206))
        assert "0.135.2" in report
        assert "0.141.1" in report
        assert "fastapi" in report
        assert "scripts/setup-ci-parity-env.sh" in report

    def test_clean_environment_says_how_many_were_checked(self):
        [line] = checker.render([], 206)
        assert "206" in line and "all satisfied" in line

    def test_detail_is_capped_and_the_remainder_counted(self):
        found = [checker.Shortfall(_declaration(name=f"pkg{i}"), "0.1") for i in range(25)]
        report = "\n".join(checker.render(found, 206, limit=10))
        assert "pkg0" in report
        assert "pkg24" not in report
        assert "15 more" in report


class TestMainExitCodes:
    def test_reporting_run_exits_zero_even_when_below_floor(self, tmp_path, monkeypatch, capsys):
        """Warn, do not gate: a below-floor box stays usable for ordinary work."""
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.135.2"})
        _write(tmp_path, "r.txt", "fastapi>=0.141.1\n")
        assert checker.main(["--root", str(tmp_path)]) == 0
        assert "0.135.2" in capsys.readouterr().out

    def test_strict_run_exits_one_when_below_floor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.135.2"})
        _write(tmp_path, "r.txt", "fastapi>=0.141.1\n")
        assert checker.main(["--root", str(tmp_path), "--strict"]) == 1

    def test_strict_run_exits_zero_when_satisfied(self, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1"})
        _write(tmp_path, "r.txt", "fastapi>=0.141.1\n")
        assert checker.main(["--root", str(tmp_path), "--strict"]) == 0

    def test_empty_enumeration_exits_two_and_says_so(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("absent.txt",))
        assert checker.main(["--root", str(tmp_path)]) == 2
        assert "no version declarations found" in capsys.readouterr().err
