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


class TestScopedRoots:
    """``--roots`` narrows the sweep to what one caller actually installs (#15130).

    ``scripts/setup-ci-parity-env.sh`` installs two of the four entry points.
    Judged against all four it looks permanently below floor, because the
    backend declarations describe packages neither it nor CI's python suite
    ever installs — so the number it reports has to be the number it can act on.
    """

    def _tree(self, tmp_path):
        _write(tmp_path, "installed.txt", "fastapi>=0.141.1\n")
        _write(tmp_path, "never-installed.txt", "sqlalchemy>=2.0.52\n")

    def test_a_narrowed_sweep_reads_only_the_named_files(self, tmp_path, monkeypatch):
        self._tree(tmp_path)
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1"})
        found, examined = checker.audit(tmp_path, ("installed.txt",))
        assert examined == 1
        assert found == []

    def test_the_same_tree_unscoped_still_reads_every_root(self, tmp_path, monkeypatch):
        """The default must not change: this option is additive, not a redefinition."""
        self._tree(tmp_path)
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("installed.txt", "never-installed.txt"))
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1"})
        _, examined = checker.audit(tmp_path)
        assert examined == 2

    def test_scoping_out_the_file_that_holds_the_shortfall_clears_it(self, tmp_path, monkeypatch):
        """The whole point: a shortfall you never installed is not your drift."""
        self._tree(tmp_path)
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1", "sqlalchemy": "2.0.51"})
        wide, _ = checker.audit(tmp_path, ("installed.txt", "never-installed.txt"))
        narrow, _ = checker.audit(tmp_path, ("installed.txt",))
        assert [shortfall.declaration.name for shortfall in wide] == ["sqlalchemy"]
        assert narrow == []

    def test_include_graph_is_still_followed_from_a_narrowed_root(self, tmp_path, monkeypatch):
        _write(tmp_path, "top.txt", "-r child.txt\nfastapi>=0.141.1\n")
        _write(tmp_path, "child.txt", "starlette>=1.6.0\n")
        monkeypatch.setattr(checker, "installed_versions", lambda names: {})
        _, examined = checker.audit(tmp_path, ("top.txt",))
        assert examined == 2

    def test_a_narrowed_sweep_that_reads_nothing_still_raises(self, tmp_path):
        """Narrowing must not become a way to reach a vacuous clean report."""
        self._tree(tmp_path)
        with pytest.raises(checker.EmptyEnumerationError):
            checker.audit(tmp_path, ("absent.txt",))

    def test_cli_passes_the_narrowed_roots_through(self, tmp_path, monkeypatch):
        self._tree(tmp_path)
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1", "sqlalchemy": "2.0.51"})
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("installed.txt", "never-installed.txt"))
        assert checker.main(["--root", str(tmp_path), "--strict"]) == 1
        assert checker.main(["--root", str(tmp_path), "--strict", "--roots", "installed.txt"]) == 0

    def test_cli_refuses_an_empty_roots_list(self, tmp_path, capsys):
        """An empty enumeration exits 2, never 0 — there was nothing to check."""
        assert checker.main(["--root", str(tmp_path), "--roots"]) == 2
        assert "nothing to check" in capsys.readouterr().err


class TestRequirePresent:
    """Absence is a shortfall only where the caller installed the file (#15130).

    The default stays "absent says nothing" — an arbitrary box not having a
    package is not evidence about CI. The parity venv is the exception: it
    installs these files, so a declaration with nothing against it means the
    install did not take, and the consequence is a silently smaller test run.
    """

    DECLARATIONS = (
        ("fastapi", ">=", "0.141.1"),
        ("docker", ">=", "7.1.0"),
    )

    def _declarations(self):
        assert self.DECLARATIONS, "no declarations to check — the cases below would be vacuous"
        return [
            _declaration(name=n, operator=o, required=r, source=f"r.txt:{i}")
            for i, (n, o, r) in enumerate(self.DECLARATIONS, 1)
        ]

    def test_absent_is_ignored_by_default(self):
        found = checker.shortfalls(self._declarations(), {"fastapi": "0.141.1"})
        assert found == []

    def test_absent_is_reported_when_required_present(self):
        found = checker.shortfalls(self._declarations(), {"fastapi": "0.141.1"}, require_present=True)
        assert [shortfall.declaration.name for shortfall in found] == ["docker"]
        assert found[0].installed == checker.ABSENT

    def test_an_absent_package_reads_as_not_installed_not_as_a_version(self):
        found = checker.shortfalls(self._declarations(), {"fastapi": "0.141.1"}, require_present=True)
        described = found[0].describe()
        assert "NOT INSTALLED" in described
        assert ">=7.1.0" in described
        assert checker.ABSENT not in described

    def test_a_below_floor_package_is_still_reported_with_its_version(self):
        """Requiring presence must not swallow the ordinary case."""
        found = checker.shortfalls(
            self._declarations(), {"fastapi": "0.135.2", "docker": "7.1.0"}, require_present=True
        )
        assert [shortfall.installed for shortfall in found] == ["0.135.2"]

    def test_cli_flag_changes_the_exit_code(self, tmp_path, monkeypatch):
        _write(tmp_path, "r.txt", "fastapi>=0.141.1\ndocker>=7.1.0\n")
        monkeypatch.setattr(checker, "DECLARATION_ROOTS", ("r.txt",))
        monkeypatch.setattr(checker, "installed_versions", lambda names: {"fastapi": "0.141.1"})
        assert checker.main(["--root", str(tmp_path), "--strict"]) == 0
        assert checker.main(["--root", str(tmp_path), "--strict", "--require-present"]) == 1


class TestLocalVersionSegments:
    """A ``+local`` build satisfies the release it is built from (#15130).

    ``setup-ci-parity-env.sh`` installs torch from the PyTorch CPU index on
    purpose, which yields ``2.13.0+cpu``. Reading that as a pre-release made it
    a permanent, false shortfall against its own ``==2.13.0`` pin.
    """

    @pytest.mark.parametrize(
        "installed,operator,required,expected",
        [
            ("2.13.0+cpu", "==", "2.13.0", True),
            ("2.13.0+cpu", ">=", "2.13.0", True),
            ("2.13.0+cpu", ">=", "2.12.0", True),
            ("2.13.0+cpu", ">=", "2.14.0", False),
            ("2.13.0+cpu", ">", "2.13.0", False),
            # The pre-release rule is untouched by the local-segment handling.
            ("1.6.0rc1", ">=", "1.6.0", False),
            ("1.6.0rc1+local", ">=", "1.6.0", False),
        ],
    )
    def test_local_segment_does_not_demote_the_release(self, installed, operator, required, expected):
        assert checker.satisfies(installed, operator, required) is expected
