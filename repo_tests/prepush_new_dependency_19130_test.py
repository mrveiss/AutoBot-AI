#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A vitest that fails only on a dependency the push ADDS is COULD NOT RUN (#19130).

Runs the hook's **own** functions (extracted verbatim) against a real throwaway git
repo, so the package.json/lockfile diff and the node_modules check are exercised end
to end. A reimplementation here would agree with itself and prove nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo

_HOOK_DIR = repo_root() / "tools" / "git-hooks"
_SOURCE = (_HOOK_DIR / "pre-push").read_text(encoding="utf-8")


def _collect_error(test_file: str, package: str) -> str:
    """vitest's own shape for a file that never loaded: `FAIL <file> [ <file> ]`."""
    return (
        f" FAIL  {test_file} [ {test_file} ]\n"
        f'Error: Failed to resolve import "{package}" from "src/x.ts". Does the file exist?\n'
    )


_ASSERTION = " FAIL  src/b.test.ts > suite > adds\nAssertionError: expected 2 to be 3\n"
_UNRESOLVED = _collect_error("src/a.test.ts", "dompurify")
_PASS_PLUS_BROKEN = _collect_error("src/a.test.ts", "vue")


def _fn(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n(?:.*\n)*?\}}$", _SOURCE, re.MULTILINE)
    assert match, f"the hook no longer defines {name} — move this test with it, do not delete it"
    return match.group(0)


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True, check=False)


def _git(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.strip()


def _repo(tmp_path: Path, *, mode: str = "manifest") -> tuple[Path, str, str]:
    """A repo whose second commit adds `dompurify`, per `mode`:

    manifest -- to app/package.json (declared); lock -- only as a TRANSITIVE lockfile key,
    package.json untouched; other -- to libs/other/package.json, a manifest app does not use.
    """
    make_repo(tmp_path)
    (tmp_path / "app").mkdir()
    manifest, lockfile = tmp_path / "app" / "package.json", tmp_path / "app" / "package-lock.json"
    manifest.write_text(json.dumps({"dependencies": {"vue": "1"}}), encoding="utf-8")
    lockfile.write_text(json.dumps({"packages": {"": {}, "node_modules/vue": {}}}), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    if mode == "lock":
        lockfile.write_text(
            json.dumps({"packages": {"node_modules/vue": {}, "node_modules/vue/node_modules/dompurify": {}}})
        )
    elif mode == "other":
        (tmp_path / "libs" / "other").mkdir(parents=True)
        (tmp_path / "libs" / "other" / "package.json").write_text(json.dumps({"dependencies": {"dompurify": "3"}}))
    else:
        manifest.write_text(json.dumps({"dependencies": {"vue": "1", "dompurify": "3"}}), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "add dep")
    return tmp_path, base, _git(tmp_path, "rev-parse", "HEAD")


def _install(root: Path, *names: str) -> Path:
    project = root / "app"
    for name in names:
        (project / "node_modules" / name).mkdir(parents=True)
        (project / "node_modules" / name / "package.json").write_text("{}", encoding="utf-8")
    return project


def _verdict(root: Path, base: str, head: str, output: str, project: Path) -> subprocess.CompletedProcess[str]:
    script = "\n".join(
        [
            f"REPO_ROOT={root}; PYTEST_PYTHON={sys.executable}; KIT_TREE=libs/autobot-ui",
            _fn("absent_added_deps"),
            _fn("vitest_failed_on_new_dep_only"),
            f'absent=$(absent_added_deps {base} {head} {project}); echo "absent=[$absent]"',
            'vitest_failed_on_new_dep_only "$1" "$absent"',
        ]
    )
    return subprocess.run(
        ["bash", "-c", script, "x", output],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=isolated_git_env(),
    )


def _stage_tool(root: Path) -> None:
    target = root / "tools" / "git-hooks"
    target.mkdir(parents=True)
    (root / "autobot_shared").symlink_to(repo_root() / "autobot_shared")
    (target / "added_js_deps.py").write_text(
        (_HOOK_DIR / "added_js_deps.py").read_text(encoding="utf-8"), encoding="utf-8"
    )


class TestAnAddedAbsentDependencyIsCouldNotRun:
    def test_added_and_absent_defers_to_ci(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        done = _verdict(root, base, head, _UNRESOLVED, _install(root, "vue"))
        assert "absent=[dompurify]" in done.stdout
        assert done.returncode == 0, done.stderr

    def test_a_transitive_only_lockfile_addition_does_not_defer(self, tmp_path: Path) -> None:
        # package.json declares nothing new: an undeclared import of a transitive package must block.
        root, base, head = _repo(tmp_path, mode="lock")
        _stage_tool(root)
        done = _verdict(root, base, head, _UNRESOLVED, _install(root, "vue"))
        assert "absent=[]" in done.stdout
        assert done.returncode != 0

    def test_a_dependency_added_to_another_projects_manifest_does_not_defer(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path, mode="other")
        _stage_tool(root)
        done = _verdict(root, base, head, _UNRESOLVED, _install(root, "vue"))
        assert "absent=[]" in done.stdout
        assert done.returncode != 0

    def test_the_kit_manifest_counts_for_every_project(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path, mode="other")
        (root / "libs" / "autobot-ui").mkdir(parents=True)
        (root / "libs" / "autobot-ui" / "package.json").write_text(json.dumps({"dependencies": {"zod": "3"}}))
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "kit dep")
        _stage_tool(root)
        head = _git(root, "rev-parse", "HEAD")
        done = _verdict(root, base, head, _collect_error("src/a.test.ts", "zod"), _install(root, "vue"))
        assert "absent=[zod]" in done.stdout and done.returncode == 0, done.stderr

    def test_a_collection_error_with_no_resolve_line_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = " FAIL  src/a.test.ts [ src/a.test.ts ]\nTypeError: x is not a function\n"
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0

    def test_output_with_no_fail_header_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        assert _verdict(root, base, head, "", _install(root, "vue")).returncode != 0

    def test_relative_and_builtin_imports_never_defer(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        install = _install(root, "vue")
        for spec in ("./x", "node:fs"):
            output = _collect_error("src/a.test.ts", spec)
            assert _verdict(root, base, head, output, install).returncode != 0, spec

    def test_a_trailing_error_after_an_accepted_block_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        tail = "⎯⎯⎯⎯⎯⎯⎯[1/1]⎯\n\n Test Files  1 failed (1)\nERROR: Coverage for lines (50%) does not meet global threshold (80%)\n"
        install = _install(root, "vue")
        assert _verdict(root, base, head, _UNRESOLVED + tail, install).returncode != 0
        clean = _UNRESOLVED + "⎯⎯⎯⎯⎯⎯⎯[1/1]⎯\n\n Test Files  1 failed (1)\n"
        assert _verdict(root, base, head, clean, install).returncode == 0

    def test_dependency_present_in_the_install_runs_vitest(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        done = _verdict(root, base, head, _UNRESOLVED, _install(root, "vue", "dompurify"))
        assert "absent=[]" in done.stdout
        assert done.returncode != 0, "a dependency that IS installed must not defer — vitest's failure stands"

    def test_a_broken_import_of_an_existing_module_still_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        done = _verdict(root, base, head, _PASS_PLUS_BROKEN, _install(root, "vue"))
        assert "absent=[dompurify]" in done.stdout
        assert done.returncode != 0, "an unresolved EXISTING module must never be waved through"

    def test_a_broken_existing_import_beside_the_new_dep_still_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        done = _verdict(root, base, head, _UNRESOLVED + _PASS_PLUS_BROKEN, _install(root, "vue"))
        assert done.returncode != 0

    def test_new_dep_failure_in_one_file_and_an_assertion_failure_in_another_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _UNRESOLVED + _ASSERTION
        done = _verdict(root, base, head, output, _install(root, "vue"))
        assert "absent=[dompurify]" in done.stdout
        assert done.returncode != 0, "a real test failure must not ride along with a deferred new dependency"

    def test_every_failed_file_a_new_dep_import_failure_defers(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _UNRESOLVED + _collect_error("src/c.test.ts", "dompurify/dist/purify")
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode == 0

    def test_an_unhandled_error_beside_the_new_dep_failure_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _UNRESOLVED + "Unhandled Errors\nError: boom\n"
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0

    def test_a_failure_naming_no_unresolved_import_still_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        done = _verdict(
            root, base, head, " FAIL  a.test.ts\nAssertionError: expected 2 to be 3\n", _install(root, "vue")
        )
        assert done.returncode != 0


class TestTheDeferralUsesTheExistingCouldNotRunPath:
    #: (exit var, output var, could_not_run label): the `vitest run` branch and the kit `vitest related` branch.
    _BRANCHES = (
        ("vitest_exit", "vitest_output", "vitest (${project})"),
        ("kit_exit", "kit_output", "vitest related (${project})"),
    )

    @staticmethod
    def _guards_branch(source: str, exit_var: str, out_var: str, label: str) -> bool:
        """The elif for this branch requires a non-zero exit AND the helper, then calls could_not_run."""
        pattern = (
            rf'elif \[ "\${exit_var}" != "0" \] && new_dep_absent=\$\(absent_added_deps [^\n]*\) \\\n'
            rf'\s*&& vitest_failed_on_new_dep_only "\${out_var}" "\$new_dep_absent"; then\n'
            rf'\s*could_not_run "{re.escape(label)}" \\\n[^\n]*new dependency; CI\'s npm ci verifies'
        )
        return re.search(pattern, source) is not None

    def test_each_vitest_branch_is_guarded_by_the_helper(self) -> None:
        for exit_var, out_var, label in self._BRANCHES:
            assert self._guards_branch(_SOURCE, exit_var, out_var, label), f"{label}: helper guard missing"
            failure = _SOURCE.find('fail "vitest failures', _SOURCE.find(f'"${exit_var}" != "0" ] && new_dep_absent'))
            assert failure > 0, "the failure branch must still follow the deferral"

    def test_removing_the_helper_from_either_branch_is_caught(self) -> None:
        for exit_var, out_var, label in self._BRANCHES:
            helper = f'&& vitest_failed_on_new_dep_only "${out_var}" "$new_dep_absent"; then'
            assert helper in _SOURCE
            assert not self._guards_branch(_SOURCE.replace(helper, "; then"), exit_var, out_var, label)
            assert not self._guards_branch(_SOURCE.replace(helper, "&& true; then"), exit_var, out_var, label)

    def test_the_helper_is_called_from_exactly_the_two_branches(self) -> None:
        assert _SOURCE.count('vitest_failed_on_new_dep_only "$') == 2

    def test_allow_unrunnable_semantics(self, tmp_path: Path) -> None:
        stubs = 'RED=; CLR=; warn() { echo "WARN $*" >&2; }; EXIT_CODE=0\n'
        for allow, code in (("0", "1"), ("1", "0")):
            script = (
                f'{stubs}ALLOW_UNRUNNABLE={allow}\n{_fn("could_not_run")}\ncould_not_run vitest "r"; echo $EXIT_CODE'
            )
            assert _bash(script, tmp_path).stdout.strip() == code
