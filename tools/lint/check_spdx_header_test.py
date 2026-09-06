# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SPDX header check, proved in both directions (#15817).

The per-file test was never the defect — this suite therefore spends most of
its assertions on *reach*: what the check does when it is handed nothing, a
path that is not there, or a sweep that lost the tree. Each of those exited
**0** before #15817, which is the same answer a clean tree gives.

The contrast pair is the point. ``test_a_tree_wide_sweep_below_the_floor_
refuses_a_verdict`` fails only because the floor exists: delete the
:func:`enforce_reach` call from ``main`` and its single header-carrying file
reports clean, exit 0. Its partner
``test_a_sweep_that_reaches_the_tree_passes`` fails if the floor is ever set
somewhere a legitimate sweep cannot clear.

Only ``git ls-files`` is faked, via :data:`guard.REPO_ROOT` and
``tracked_paths``. ``in_scope``, the readable/unreadable split, the floor, the
header test and the reporting all run for real against a synthetic tree.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # fixed argv, no shell, test-only
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_spdx_header.py"
_spec = importlib.util.spec_from_file_location("check_spdx_header", _MODULE_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

_HEADED = "# Copyright 2025-2026 mrveiss\n# SPDX-License-Identifier: Apache-2.0\nvalue = 1\n"
_HEADLESS = "value = 1\n"


@pytest.fixture
def sweep(monkeypatch, tmp_path):
    """Point ``--all`` at a synthetic tree of ``{relative path: body}``."""

    def _build(files: dict[str, str]) -> Path:
        for rel, body in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(guard, "tracked_paths", lambda root, *patterns: list(files))
        return tmp_path

    return _build


def _write(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


class TestAnInvocationThatExaminesNothingFails:
    """Exit 0 is a claim. A check that saw nothing has no standing to make it."""

    def test_no_arguments_refuses_a_verdict(self):
        assert guard.main([]) == guard.EXIT_NO_VERDICT

    def test_a_file_list_that_resolves_to_nothing_examinable_refuses_a_verdict(self, tmp_path):
        out_of_scope = _write(tmp_path, "notes.md", "# not source\n")
        assert guard.main([out_of_scope]) == guard.EXIT_NO_VERDICT

    def test_an_empty_xargs_split_refuses_a_verdict(self):
        """The CI shape #15817 was filed about, end to end through the real binary.

        ``git ls-files -z | xargs -0`` invokes the command once with no
        arguments when the pipeline produces nothing, which is how a shallow
        checkout or a wrong CWD used to pass the gate having read no file.
        """
        result = subprocess.run(  # nosec B603  # fixed argv, no shell
            [sys.executable, str(_MODULE_PATH)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == guard.EXIT_NO_VERDICT
        assert "examined=0" in result.stderr

    def test_fix_mode_tolerates_an_all_excluded_file_list(self, tmp_path):
        """The single-file-commit carve-out, asserted so it stays deliberate.

        ``--fix`` is an action, not a verdict: "nothing needed fixing" is a
        real outcome. The pre-commit hook is the only ``--fix`` caller and it
        must survive a staged file EXCLUDE_RE skips but its own filter let
        through, or it is disabled within a day.
        """
        out_of_scope = _write(tmp_path, "notes.md", "# not source\n")
        assert guard.main(["--fix", out_of_scope]) == 0


class TestAnUnreadablePathIsAnErrorNotAPass:
    """A renamed or mistyped path used to vanish silently — the stale-tree read."""

    def test_a_nonexistent_in_scope_path_exits_non_zero_naming_it(self, capsys, tmp_path):
        absent = str(tmp_path / "never_written.py")
        assert guard.main([absent]) == guard.EXIT_NO_VERDICT
        assert absent in capsys.readouterr().err

    def test_it_does_not_share_an_exit_code_with_a_missing_header(self, tmp_path):
        headless = _write(tmp_path, "headless.py", _HEADLESS)
        absent = str(tmp_path / "never_written.py")
        assert guard.main([headless]) == 1
        assert guard.main([absent]) != 1

    def test_an_out_of_scope_path_that_is_absent_stays_merely_uncounted(self, tmp_path):
        """A wrong extension is not this check's business; a missing ``.py`` is."""
        headed = _write(tmp_path, "headed.py", _HEADED)
        assert guard.main([headed, str(tmp_path / "gone.md")]) == 0


class TestTheReachFloor:
    """Bound to files examined, never to violations found."""

    def test_a_tree_wide_sweep_below_the_floor_refuses_a_verdict(self, sweep):
        """MUTATION TARGET. Delete the ``enforce_reach`` call and this returns 0.

        One file, and it carries a valid header, so nothing is missing and the
        per-file logic reports clean. Only the floor distinguishes "the tree is
        fine" from "I never reached the tree".
        """
        sweep({"only.py": _HEADED})
        assert guard.main(["--all"]) == guard.EXIT_NO_VERDICT

    def test_a_sweep_that_reaches_the_tree_passes(self, sweep, monkeypatch):
        """The other half of the contrast pair."""
        monkeypatch.setattr(guard, "SPDX_FLOOR", 3)
        sweep({"a.py": _HEADED, "b.ts": _HEADED, "c.sh": _HEADED})
        assert guard.main(["--all"]) == 0

    def test_the_live_tree_clears_the_floor(self):
        """A floor the real sweep only just reaches asserts nothing."""
        reached = len(guard._tree_wide_candidates())
        assert reached >= guard.SPDX_FLOOR, f"tree-wide sweep reached only {reached} file(s)"

    def test_the_floor_does_not_fire_on_a_single_file_commit(self, tmp_path):
        """pre-commit passes staged files; a floor there reddens every small PR."""
        headed = _write(tmp_path, "one.py", _HEADED)
        assert guard.main([headed]) == 0

    def test_all_refuses_an_explicit_file_list(self):
        """``--all`` enumerates the tree itself; mixing the two hides which won."""
        assert guard.main(["--all", "README.md"]) == guard.EXIT_NO_VERDICT


class TestAFailedEnumerationIsNotAVerdictAboutTheTree:
    """#15819 review: enumeration failing must not read as "headers are missing"."""

    def test_a_raising_enumeration_returns_no_verdict(self, monkeypatch):
        """MUTATION TARGET. Drop the try/except in ``main`` and this returns 1.

        ``tracked_paths`` raises rather than returning ``[]``, so the failure
        arrives as an exception. An unhandled one exits **1**, and 1 already
        means "headers are missing" -- a claim about the tree. Enumeration
        failing is the opposite claim: the tree could not be read at all.
        Collapsing them would undo the separation this check exists to make.
        """

        def _boom() -> list:
            raise OSError("git ls-files unavailable")

        monkeypatch.setattr(guard, "_tree_wide_candidates", _boom)
        assert guard.main(["--all"]) == guard.EXIT_NO_VERDICT

    def test_it_does_not_share_an_exit_code_with_a_missing_header(self, monkeypatch, sweep):
        """The contrast half: a real missing header still exits 1, not 2."""
        monkeypatch.setattr(guard, "SPDX_FLOOR", 1)
        sweep({"bare.py": "x = 1\n"})
        assert guard.main(["--all"]) == 1


class TestTheHeaderCheckItselfIsUnchanged:
    """Every file that passed before #15817 still passes; the detection is correct."""

    def test_a_headerless_file_still_fails(self, tmp_path):
        assert guard.main([_write(tmp_path, "headless.py", _HEADLESS)]) == 1

    def test_a_headed_file_still_passes(self, tmp_path):
        assert guard.main([_write(tmp_path, "headed.py", _HEADED)]) == 0

    def test_a_tree_wide_sweep_finds_a_planted_headerless_file(self, sweep, monkeypatch):
        """The planted-violation direction, through the floored ``--all`` path."""
        monkeypatch.setattr(guard, "SPDX_FLOOR", 2)
        sweep({"good.py": _HEADED, "bad.py": _HEADLESS})
        assert guard.main(["--all"]) == 1

    def test_fix_inserts_the_header_below_a_shebang(self, tmp_path):
        target = _write(tmp_path, "script.py", "#!/usr/bin/env python3\nvalue = 1\n")
        assert guard.main(["--fix", target]) == 0
        lines = Path(target).read_text(encoding="utf-8").splitlines()
        assert lines[0] == "#!/usr/bin/env python3"
        assert guard.SPDX_LINE in lines[2]


class TestTheCountIsReported:
    """Reach made visible, not merely enforced."""

    @pytest.mark.parametrize("count", [0, 1, 2])
    def test_every_run_prints_how_many_files_it_examined(self, capsys, tmp_path, count):
        argv = [_write(tmp_path, f"f{i}.py", _HEADED) for i in range(count)]
        guard.main(argv)
        assert f"examined={count}" in capsys.readouterr().err
