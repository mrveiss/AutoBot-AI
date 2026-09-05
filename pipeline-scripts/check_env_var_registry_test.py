# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The env-registry checker's refusals and its discrimination (#13200).

``check_env_var_registry_helpers_test.py`` covers one axis: that every spelling
of an env read is *seen*. This file covers the other two, which nothing pinned:

* **The refusal.** ``_env_reader_names`` calls ``sys.exit`` when it derives an
  empty helper set, because an empty set silently disables half the check.
  That line was reachable but unasserted -- a refusal nothing tests is a
  refusal that can be deleted, or inverted, without a single test going red.
* **The negative cases.** A checker that flags everything passes every
  "does it catch X" test ever written. The discrimination tests below are what
  separate "sees the read" from "reports the read", and they are the half that
  fails when a matcher is widened carelessly.

Loaded per test through ``importlib`` rather than imported once: several of
these mutate module-level state (the ``lru_cache`` on ``_env_reader_names``,
``_ENV_UTILS``), and a shared module object would leak that between tests.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_env_var_registry.py")


@pytest.fixture
def checker():
    """A freshly executed copy of the checker module."""
    spec = importlib.util.spec_from_file_location("check_env_var_registry_13200", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample(checker, tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(textwrap.dedent(source), encoding="utf-8")
    return [name for _, name in checker._extract_autobot_getenv_names(target)]


# ---------------------------------------------------------------------------
# The refusal: an empty helper set must stop the run, not shrink the check
# ---------------------------------------------------------------------------


def test_an_empty_helper_set_refuses_rather_than_checking_half_the_tree(checker, tmp_path):
    """``env_utils`` with no ``env_*(name, ...)`` helpers is not "no helpers to
    check" -- it is the module having moved, been renamed, or failed to parse.
    Continuing would drop every helper-form read from the scan and report the
    remaining ``os.getenv`` sites as full coverage, which is #14265 again.
    """
    empty = tmp_path / "env_utils.py"
    empty.write_text("def unrelated(value):\n    return value\n", encoding="utf-8")
    checker._ENV_UTILS = empty
    checker._env_reader_names.cache_clear()

    with pytest.raises(SystemExit) as excinfo:
        checker._env_reader_names()

    message = str(excinfo.value)
    assert "no env-reading helpers found" in message
    assert "refusing to check half the tree" in message


def test_a_helper_whose_first_argument_is_not_name_does_not_count(checker, tmp_path):
    """The derivation is a shape test, not a prefix test.

    ``env_snapshot()`` starts with ``env_`` but takes no variable name, so it
    reads nothing a registry could cover. Counting it would satisfy the floor
    above with a function that proves nothing.
    """
    decoy = tmp_path / "env_utils.py"
    decoy.write_text("def env_snapshot(mapping):\n    return dict(mapping)\n", encoding="utf-8")
    checker._ENV_UTILS = decoy
    checker._env_reader_names.cache_clear()

    with pytest.raises(SystemExit):
        checker._env_reader_names()


def test_the_real_env_utils_satisfies_the_refusal(checker):
    """The other direction: the refusal must not be firing on the live tree.

    A guard that raises everywhere is indistinguishable from a guard that is
    broken, and this one exits the process.
    """
    checker._env_reader_names.cache_clear()
    assert len(checker._env_reader_names()) >= 5


# ---------------------------------------------------------------------------
# Discrimination -- what must NOT be reported
# ---------------------------------------------------------------------------


def test_a_name_the_file_sets_for_itself_is_not_reported(checker, tmp_path):
    """A fixture is not deployed configuration. Registering it would document a
    variable no deployment ever sets."""
    assert (
        _sample(
            checker,
            tmp_path,
            """
            def test_blank(monkeypatch):
                monkeypatch.setenv("AUTOBOT_FIXTURE_ONLY", "x")
                return env_str("AUTOBOT_FIXTURE_ONLY", "")
            """,
        )
        == []
    )


def test_a_non_literal_variable_name_is_not_reported(checker, tmp_path):
    """``os.getenv(name)`` carries no constant to check against the registry.
    Reporting the call anyway would name no variable a reviewer could act on."""
    assert _sample(checker, tmp_path, 'import os\n\ndef read(name):\n    return os.getenv(name, "")\n') == []


def test_a_bare_getenv_with_no_arguments_is_not_reported(checker, tmp_path):
    assert _sample(checker, tmp_path, "import os\n\nx = os.getenv()\n") == []


def test_a_file_that_does_not_parse_yields_nothing_rather_than_raising(checker, tmp_path):
    """A syntax error is another hook's finding. This one must not turn it into
    a traceback that hides every other file's result."""
    assert _sample(checker, tmp_path, "def broken(:\n") == []


def test_the_registry_module_itself_is_skipped(checker):
    """``env_registry.py`` names every variable in the repository. Scanning it
    would report the registry as its own violation."""
    assert checker._is_registry_file(Path("autobot_shared/env_registry.py"))
    assert not checker._is_registry_file(Path("autobot_shared/env_utils.py"))


# ---------------------------------------------------------------------------
# Discrimination -- what MUST be reported
# ---------------------------------------------------------------------------


def test_an_unregistered_autobot_variable_fails_the_run(checker, tmp_path):
    """The positive control for every negative above: with the exemptions out of
    the way, an ordinary unregistered read still blocks."""
    target = tmp_path / "offender.py"
    target.write_text('import os\n\nx = os.getenv("AUTOBOT_DEFINITELY_NOT_REGISTERED", "")\n', encoding="utf-8")
    assert "AUTOBOT_DEFINITELY_NOT_REGISTERED" not in checker.REGISTRY
    assert checker.main([str(target)]) == 1


def test_a_registered_variable_passes(checker, tmp_path):
    """Guards the same path in the green direction, so a checker that failed
    every file could not satisfy the test above."""
    registered = sorted(checker.REGISTRY)[0]
    target = tmp_path / "clean.py"
    target.write_text(f'import os\n\nx = os.getenv("{registered}", "")\n', encoding="utf-8")
    assert checker.main([str(target)]) == 0


def test_a_non_python_argv_checks_nothing_and_does_not_touch_the_docs(checker, tmp_path):
    """pre-commit passes whatever was staged. A markdown-only commit must not
    fail on a docs table it did not change."""
    target = tmp_path / "notes.md"
    target.write_text("nothing to see\n", encoding="utf-8")
    assert checker.main([str(target)]) == 0


# ---------------------------------------------------------------------------
# The docs half
# ---------------------------------------------------------------------------


def test_missing_markers_are_a_violation_not_a_pass(checker, tmp_path, monkeypatch):
    """With the markers gone there is no section to compare, so a naive
    implementation compares "" to "" and reports the docs fresh."""
    docs = tmp_path / "CLAUDE_RULES.md"
    docs.write_text("# Rules\n\nNo autogenerated section here.\n", encoding="utf-8")
    monkeypatch.setattr(checker, "DOCS_PATH", docs)

    violations = checker.check_docs_freshness()

    assert violations
    assert "magic markers missing" in violations[0]


def test_an_absent_docs_file_is_a_violation(checker, tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "DOCS_PATH", tmp_path / "gone.md")
    assert checker.check_docs_freshness() == [f"docs: {tmp_path / 'gone.md'} not found"]


def test_a_stale_table_is_a_violation(checker, tmp_path, monkeypatch):
    docs = tmp_path / "CLAUDE_RULES.md"
    docs.write_text(
        f"{checker.BEGIN_MARKER}\n| Name |\n|---|\n| `AUTOBOT_STALE` |\n{checker.END_MARKER}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "DOCS_PATH", docs)

    violations = checker.check_docs_freshness()

    assert violations
    assert "stale" in violations[0]


def test_the_live_docs_table_is_current(checker):
    """The generated table and the checked-in one must already agree, or every
    commit in the repository is failing this hook right now."""
    assert checker.check_docs_freshness() == []


def test_a_pipe_in_a_description_is_escaped(checker):
    """An unescaped ``|`` splits the markdown row, so the rendered table shifts
    every later column by one and the docs silently misdescribe a variable."""
    spec = next(iter(checker.REGISTRY.values()))

    class _Piped:
        component = spec.component
        type = str
        default = ""
        range = None
        description = "before | after"

    table = checker._build_table({"AUTOBOT_PIPE": _Piped()})

    assert "before \\| after" in table
    assert "| before | after |" not in table


# ---------------------------------------------------------------------------
# The baseline is a ceiling, not a hiding place
# ---------------------------------------------------------------------------


def test_a_baselined_name_that_got_registered_is_reported(checker, monkeypatch):
    """A stranded entry exempts whatever arrives under that name next, silently
    -- the #14236 failure. It must be reported, not quietly filtered."""
    registered = sorted(checker.REGISTRY)[0]
    monkeypatch.setattr(checker, "_UNREGISTERED_BASELINE", frozenset({registered}))

    stale = checker._stale_baseline_entries()

    assert len(stale) == 1
    assert registered in stale[0]


def test_a_baselined_name_still_unregistered_is_not_reported(checker, monkeypatch):
    """The other direction, so the test above cannot be satisfied by a function
    that reports every baseline entry."""
    monkeypatch.setattr(checker, "_UNREGISTERED_BASELINE", frozenset({"AUTOBOT_NEVER_REGISTERED_ANYWHERE"}))
    assert checker._stale_baseline_entries() == []


# ---------------------------------------------------------------------------
# Full-repo sweep (#15807). Before it, `main([])` inspected nothing and returned
# 0, so "the registry is clean" and "no files were handed to the checker" were
# the same answer. Every fixture below is synthetic: a sweep proved only against
# the live tree passes vacuously the moment the tree is clean, which it is.
# ---------------------------------------------------------------------------
def _sweep_over(checker, monkeypatch, files: dict[str, str], tmp_path: Path) -> int:
    """Run the no-argument sweep over exactly *files*, and nothing else."""
    written = []
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(body), encoding="utf-8")
        # Absolute: `repo_root / "/abs"` is `/abs` in pathlib, so the sweep reads
        # exactly these files and nothing from the real tree.
        written.append(str(target))
    monkeypatch.setattr(checker, "_discover_python_files", lambda root: written)
    monkeypatch.setattr(checker, "MIN_SCANNED_PY_FILES", 1)
    monkeypatch.setattr(checker, "check_docs_freshness", lambda: [])
    return checker.main([])


def test_the_sweep_finds_an_unregistered_read(checker, monkeypatch, tmp_path):
    """The defect the sweep exists for: a reader nobody staged."""
    exit_code = _sweep_over(
        checker,
        monkeypatch,
        {"reader.py": "import os\n\nX = os.getenv('AUTOBOT_NOT_REGISTERED_ANYWHERE', '1')\n"},
        tmp_path,
    )

    assert exit_code == 1


def test_the_sweep_accepts_a_registered_read(checker, monkeypatch, tmp_path):
    """The contrast, so the sweep cannot pass by rejecting everything."""
    registered = sorted(checker.REGISTRY)[0]
    exit_code = _sweep_over(
        checker,
        monkeypatch,
        {"reader.py": f"import os\n\nX = os.getenv('{registered}', '1')\n"},
        tmp_path,
    )

    assert exit_code == 0


def test_a_registration_dropped_while_its_reader_is_untouched_is_caught(checker, monkeypatch, tmp_path):
    """The merge case, which a staged-file check structurally cannot see.

    Two PRs each append a registration to the same module, so they conflict by
    construction; `-X ours` resolves to a file that compiles, imports and passes
    every test while dropping one. The staged file is the *registry* — the file
    that reads the dropped variable is untouched, so the pre-commit hook never
    looks at it. Only a sweep does.
    """
    dropped = sorted(checker.REGISTRY)[0]
    monkeypatch.setattr(checker, "REGISTRY", {k: v for k, v in checker.REGISTRY.items() if k != dropped})

    exit_code = _sweep_over(
        checker,
        monkeypatch,
        {"untouched_reader.py": f"import os\n\nX = os.getenv('{dropped}', '1')\n"},
        tmp_path,
    )

    assert exit_code == 1, f"a reader of the dropped {dropped} was not reported"


def test_a_sweep_that_reaches_too_few_files_fails(checker, monkeypatch):
    """A glob that silently matches nothing prints the same clean line as a
    clean tree — the defect this whole issue is about, one level down."""
    monkeypatch.setattr(checker, "_discover_python_files", lambda root: [])
    monkeypatch.setattr(checker, "MIN_SCANNED_PY_FILES", 10)

    assert checker.main([]) == 1


def test_the_live_tree_is_above_the_reach_floor(checker):
    """The floor is only meaningful if the real sweep clears it comfortably."""
    repo_root = Path(__file__).resolve().parents[1]
    discovered = checker._discover_python_files(repo_root)

    assert len(discovered) >= checker.MIN_SCANNED_PY_FILES, f"only {len(discovered)} tracked .py files reached"
