# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push hook hands vitest only files under a vitest include root (#18694).

A changed Playwright spec (`autobot-frontend/tests/visual/storybook-stories.spec.ts`)
matched the hook's `*.spec.ts` selector. vitest's config excludes `tests/**`, so
`vitest run <that file>` collected nothing, and the push was blocked as COULD NOT RUN.
"""

from __future__ import annotations

import re
import subprocess

import pytest
from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_CONFIGS = ("autobot-frontend", "autobot-slm-frontend", "libs/autobot-ui")
_ROOTS_FN = re.compile(r"^vitest_include_roots\(\) \{$.*?^\}$", re.MULTILINE | re.DOTALL)
_SELECTION = re.compile(r"^    vitest_roots=\$\(.*?^    test_files=.*?$", re.MULTILINE | re.DOTALL)
#: The two include shapes in the tree: autobot-frontend's src/ + scripts/, and src/ alone.
_SRC_AND_SCRIPTS = "include: [\n  'src/**/*.spec.ts',\n  'scripts/**/*.spec.ts',\n],"
_SRC_ONLY = "include: ['src/**/*.{test,spec}.ts'],"
_INCLUDE = re.compile(r"include:\s*\[(.*?)\]", re.DOTALL)


def _hook() -> str:
    return _HOOK.read_text(encoding="utf-8")


def _include_roots(project: str) -> set[str]:
    source = (repo_root() / project / "vitest.config.ts").read_text(encoding="utf-8")
    globs = re.findall(r"'([^']+)'", _INCLUDE.search(source).group(1))
    return {g.split("/", 1)[0] for g in globs}


def _hook_roots(project_dir) -> str:
    script = _ROOTS_FN.search(_hook()).group(0) + '\nvitest_include_roots "$1"'
    run = subprocess.run(["bash", "-c", script, "_", str(project_dir)], capture_output=True, text=True, check=True)
    return run.stdout.strip()


@pytest.mark.parametrize("project", _CONFIGS)
def test_the_hook_reads_each_projects_own_include_roots(project):
    roots = re.fullmatch(r"\^\((.+)\)/", _hook_roots(repo_root() / project)).group(1)
    assert set(roots.split("|")) == _include_roots(project)


def test_an_unreadable_config_selects_nothing(tmp_path):
    assert _hook_roots(tmp_path) == "^$"


def _select(tmp_path, changed: list[str], include: str = _SRC_AND_SCRIPTS) -> tuple[list[str], str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "vitest.config.ts").write_text(f"export default {{ test: {{ {include} }} }}\n", encoding="utf-8")
    for rel in changed:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    script = "\n".join(
        [
            _ROOTS_FN.search(_hook()).group(0),
            'log() { echo "$*" >&2; }',
            'project=app; project_dir="$1"',
            "project_changed=$(printf 'app/%s\\n' " + " ".join(f"'{c}'" for c in changed) + ")",
            _SELECTION.search(_hook()).group(0),
            'echo "$test_files"',
        ]
    )
    run = subprocess.run(["bash", "-c", script, "_", str(tmp_path)], capture_output=True, text=True, check=True)
    return [line for line in run.stdout.splitlines() if line], run.stderr


def test_a_scripts_spec_is_run_only_where_the_config_collects_scripts(tmp_path):
    """autobot-slm-frontend collects src/ only: its scripts/*.spec.ts is named, not handed to vitest."""
    assert _select(tmp_path / "fe", ["scripts/example.spec.ts"], _SRC_AND_SCRIPTS)[0] == ["scripts/example.spec.ts"]
    got, stderr = _select(tmp_path / "slm", ["scripts/example.spec.ts"], _SRC_ONLY)
    assert got == [] and "scripts/example.spec.ts" in stderr


@pytest.mark.parametrize(
    "changed, selected",
    [
        (["src/a.spec.ts", "tests/visual/storybook-stories.spec.ts"], ["src/a.spec.ts"]),
        (["scripts/b.test.ts", "e2e/flow.spec.ts"], ["scripts/b.test.ts"]),
        (["tests/visual/only.spec.ts"], []),
    ],
)
def test_only_include_root_files_reach_vitest(tmp_path, changed, selected):
    got, stderr = _select(tmp_path, changed)
    assert got == selected
    skipped = sorted(set(changed) - set(selected))
    assert all(s in stderr for s in skipped), "a skipped spec must be named, not dropped silently"
