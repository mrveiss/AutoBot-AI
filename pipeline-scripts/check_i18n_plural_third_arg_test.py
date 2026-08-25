#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The i18n plural hook must BLOCK on a violation, and must not block on a lookalike (#13200).

This hook stops every commit that touches a `.ts` or `.vue` file, and it had no
test at all. A false positive in it halts work repo-wide until someone edits the
checker; a false negative lets the #6976 regression back in. Both directions are
driven here through the real ``main`` with real files on disk and the real
``en.json``, asserting the process exit code rather than an internal return
value — blocking is the behaviour, so blocking is what is asserted.

The negative cases are the ones the other checkers only learned by running
against real code (#13200 records two such classes for the `open()` hook): a
key that merely *looks* plural, a second argument carrying a comma inside a
nested literal, and a string argument containing a bracket.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("check_i18n_plural_third_arg.py")
EN_JSON = REPO_ROOT / "autobot-frontend" / "src" / "i18n" / "locales" / "en.json"


def _load_script():
    """Load the checker leaving no ``sys.modules`` entry behind (#13337)."""
    spec = importlib.util.spec_from_file_location("check_i18n_plural_third_arg", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker():
    return _load_script()


@pytest.fixture
def plural_key(checker):
    """A key that really is plural in this repository's en.json.

    Derived, never hardcoded: a literal key would rot the day it is renamed and
    the whole suite would then exercise a key the checker ignores — passing for
    the wrong reason.
    """
    keys = sorted(checker._load_plural_keys())
    assert keys, "en.json carries no plural key; this suite would assert nothing"
    return keys[0]


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


class TestTheHookBlocks:
    """The point of a commit-blocking checker is the non-zero exit."""

    def test_a_missing_third_arg_exits_non_zero(self, checker, plural_key, tmp_path):
        target = _write(tmp_path, "Bad.vue", f"const label = t('{plural_key}', {{ count: n }})\n")

        assert checker.main([str(target)]) == 1

    def test_the_message_names_the_file_the_line_and_the_key(self, checker, plural_key, tmp_path, capsys):
        target = _write(tmp_path, "Bad.vue", f"// header\nconst label = t('{plural_key}', {{ count: n }})\n")

        checker.main([str(target)])

        printed = capsys.readouterr().out
        assert f"{target}:2:" in printed
        assert plural_key in printed

    def test_it_blocks_when_run_as_the_hook_runs_it(self, plural_key, tmp_path):
        """pre-commit invokes the file, so prove the process itself exits non-zero."""
        target = _write(tmp_path, "Bad.ts", f"t('{plural_key}', {{ count: n }})\n")

        result = subprocess.run(  # nosec B603
            [sys.executable, str(SCRIPT), str(target)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stdout + result.stderr

    def test_the_dollar_t_spelling_is_caught_too(self, checker, plural_key, tmp_path):
        target = _write(tmp_path, "Bad.vue", f"{{{{ $t('{plural_key}', {{ count: n }}) }}}}\n")

        assert checker.main([str(target)]) == 1

    def test_a_call_wrapped_across_lines_is_caught(self, checker, plural_key, tmp_path):
        body = f"const label = t(\n  '{plural_key}',\n  {{ count: n }}\n)\n"
        target = _write(tmp_path, "Wrapped.vue", body)

        assert checker.main([str(target)]) == 1


class TestTheHookDoesNotBlockOnALookalike:
    """A false positive here halts every commit in the repository."""

    def test_a_correct_call_passes(self, checker, plural_key, tmp_path):
        target = _write(tmp_path, "Good.vue", f"const label = t('{plural_key}', {{ count: n }}, n)\n")

        assert checker.main([str(target)]) == 0

    def test_a_non_plural_key_is_ignored(self, checker, tmp_path):
        target = _write(tmp_path, "Plain.vue", "const label = t('definitely.not.a.plural.key', { count: n })\n")

        assert checker.main([str(target)]) == 0

    def test_a_comma_inside_the_second_argument_is_not_a_third_argument(
        self, checker, plural_key, tmp_path
    ):
        """`{ count: n, total: m }` has a comma, but not a top-level one."""
        target = _write(tmp_path, "Nested.vue", f"t('{plural_key}', {{ count: n, total: m }})\n")

        assert checker.main([str(target)]) == 1

    def test_a_nested_call_in_the_second_argument_still_needs_a_count(
        self, checker, plural_key, tmp_path
    ):
        target = _write(tmp_path, "Call.vue", f"t('{plural_key}', {{ count: fmt(a, b) }})\n")

        assert checker.main([str(target)]) == 1

    def test_a_third_argument_after_a_nested_literal_is_accepted(self, checker, plural_key, tmp_path):
        target = _write(tmp_path, "Ok.vue", f"t('{plural_key}', {{ count: fmt(a, b) }}, n)\n")

        assert checker.main([str(target)]) == 0

    def test_a_bracket_inside_a_string_argument_does_not_confuse_the_scan(
        self, checker, plural_key, tmp_path
    ):
        target = _write(tmp_path, "Str.vue", f"t('{plural_key}', {{ label: ')' }}, n)\n")

        assert checker.main([str(target)]) == 0

    def test_a_file_of_another_type_is_not_inspected(self, checker, plural_key, tmp_path):
        """The hook's `files:` filter is `\\.(ts|vue)$`; the script must agree with it."""
        target = _write(tmp_path, "Bad.py", f"t('{plural_key}', {{ count: n }})\n")

        assert checker.main([str(target)]) == 0

    def test_an_unreadable_file_is_skipped_rather_than_crashing(self, checker, tmp_path):
        assert checker.main([str(tmp_path / "absent.vue")]) == 0


class TestTheKeySetIsNotSilentlyEmpty:
    """"No violation found" must stay distinguishable from "nothing to look for".

    The checker used to return an empty key set on any error and ``main`` turned
    that straight into exit 0, so an unreadable en.json made the hook pass every
    file while still reporting success — the emptied-allowlist shape (#13200).
    """

    def test_the_repository_really_has_plural_keys(self, checker):
        assert checker._load_plural_keys(), (
            "en.json yields no plural key, so this hook currently inspects nothing "
            "and every test above would pass vacuously"
        )

    def test_an_unreadable_locale_file_blocks_rather_than_passing(self, checker, tmp_path, monkeypatch):
        monkeypatch.setattr(checker, "_EN_JSON", tmp_path / "gone.json")

        with pytest.raises(checker.PluralKeysUnavailable):
            checker._load_plural_keys()

    def test_an_unparseable_locale_file_blocks_rather_than_passing(self, checker, tmp_path, monkeypatch):
        broken = _write(tmp_path, "en.json", "{not json")
        monkeypatch.setattr(checker, "_EN_JSON", broken)

        assert checker.main([]) == 1

    def test_a_locale_file_with_no_plural_key_blocks_rather_than_passing(
        self, checker, tmp_path, monkeypatch
    ):
        empty = _write(tmp_path, "en.json", json.dumps({"a": {"b": "no separator here"}}))
        monkeypatch.setattr(checker, "_EN_JSON", empty)

        assert checker.main([]) == 1

    def test_a_nested_plural_key_is_collected_with_its_dotted_path(self, checker):
        collected = checker._collect_plural_keys({"a": {"b": "one | many", "c": "single"}})

        assert collected == {"a.b"}


class TestHookWiring:
    """A checker the config stopped calling blocks nothing."""

    def test_the_pre_commit_config_still_wires_this_checker(self):
        config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        assert SCRIPT.name in config, (
            f"{SCRIPT.name} is no longer referenced by .pre-commit-config.yaml — it blocks nothing"
        )

    def test_the_locale_file_the_checker_reads_exists(self):
        assert EN_JSON.exists(), f"{EN_JSON} is missing; the checker would block every commit"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
