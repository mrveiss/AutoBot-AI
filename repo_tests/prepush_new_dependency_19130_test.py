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
        # Twice each: the added-dependency deferral and the #19472 stale-install one.
        assert _SOURCE.count('vitest_failed_on_new_dep_only "$') == 4
        assert _SOURCE.count('"$stale_deps $new_dep_absent"') == 3

    def test_allow_unrunnable_semantics(self, tmp_path: Path) -> None:
        stubs = 'RED=; CLR=; warn() { echo "WARN $*" >&2; }; EXIT_CODE=0\n'
        for allow, code in (("0", "1"), ("1", "0")):
            script = (
                f'{stubs}ALLOW_UNRUNNABLE={allow}\n{_fn("could_not_run")}\ncould_not_run vitest "r"; echo $EXIT_CODE'
            )
            assert _bash(script, tmp_path).stdout.strip() == code


def _grouped(files: list[str], package: str) -> str:
    """vitest's dedupe of one identical collection error: every header, then the error once."""
    headers = "".join(f" FAIL  {f} [ {f} ]\n" for f in files)
    return headers + f'Error: Failed to resolve import "{package}" from "../libs/x.ts". Does the file exist?\n'


class TestVitestGroupedCollectionErrors:
    """#19130 follow-up: a kit change failed 46 files under ONE shared error, and the per-header
    check closed 45 of them with no error seen, so the deferral never applied."""

    def test_a_grouped_new_dep_error_defers(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _grouped(["src/a.test.ts", "src/b.test.ts", "src/c.test.ts"], "dompurify") + "⎯⎯⎯[1/1]⎯\n"
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode == 0

    def test_a_grouped_error_naming_an_existing_module_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _grouped(["src/a.test.ts", "src/b.test.ts"], "vue")
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0

    def test_an_assertion_header_inside_a_group_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = " FAIL  src/b.test.ts > suite > adds\n" + _grouped(["src/a.test.ts"], "dompurify")
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0

    def test_an_assertion_header_inside_a_shared_error_group_fails(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = " FAIL  src/a.test.ts [ src/a.test.ts ]\n FAIL  src/b.test.ts > suite > adds\n" + _grouped(
            ["src/c.test.ts"], "dompurify"
        )
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0

    def test_a_coloured_grouped_new_dep_error_defers(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        red, dim, clr = "\x1b[31m", "\x1b[2m", "\x1b[39m\x1b[22m"
        plain = _grouped(["src/a.test.ts", "src/b.test.ts"], "dompurify")
        output = (
            plain.replace(" FAIL ", f" {red}FAIL{clr} ").replace("Error:", f"{red}Error{clr}:") + f"{dim}⎯[1/2]⎯{clr}\n"
        )
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode == 0

    def test_a_header_after_a_block_body_still_needs_its_own_error(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        output = _UNRESOLVED + "  Plugin: vite:import-analysis\n FAIL  src/z.test.ts [ src/z.test.ts ]\n"
        assert _verdict(root, base, head, output, _install(root, "vue")).returncode != 0


def _tsc_verdict(diagnostics: str, absent: str, tmp_path: Path) -> int:
    script = f'{_fn("tsc_failed_on_new_dep_only")}\ntsc_failed_on_new_dep_only "$1" "$2"'
    return subprocess.run(
        ["bash", "-c", script, "x", diagnostics, absent], cwd=tmp_path, capture_output=True, check=False
    ).returncode


def _vitest_verdict(output: str, absent: str, tmp_path: Path) -> int:
    script = f'{_fn("vitest_failed_on_new_dep_only")}\nvitest_failed_on_new_dep_only "$1" "$2"'
    return subprocess.run(
        ["bash", "-c", script, "x", output, absent], cwd=tmp_path, capture_output=True, check=False
    ).returncode


class TestARelativeSpecifierNeverDefers:
    """The `pkg ~ /^[.\\/]/` guard: a relative or absolute specifier's first segment is `.`, `..` or empty,
    never a valid npm name, so the absent-name check alone rejects it today. These pin the guard itself:
    a manifest key that is not a package name must still not defer a relative import."""

    def test_vitest_relative_import_with_a_dotdot_absent_name_fails(self, tmp_path: Path) -> None:
        output = _grouped(["src/a.test.ts"], "../missing")
        assert _vitest_verdict(output, "..", tmp_path) != 0

    def test_tsc_relative_module_with_a_dotdot_absent_name_fails(self, tmp_path: Path) -> None:
        line = TestVueTscNewDependency._TS2307.format("../missing")
        assert _tsc_verdict(line, "..", tmp_path) != 0


class TestVueTscNewDependency:
    """#19130 follow-up: vue-tsc blocked the same push on TS2307 for the added-and-absent package."""

    _TS2307 = "../libs/autobot-ui/src/utils/sanitize.ts(12,23): error TS2307: Cannot find module '{0}' or its corresponding type declarations."

    def test_ts2307_for_the_absent_new_dep_defers(self, tmp_path: Path) -> None:
        lines = "\n".join([self._TS2307.format("dompurify"), self._TS2307.format("dompurify/dist/purify")])
        assert _tsc_verdict(lines, "dompurify", tmp_path) == 0

    def test_any_other_diagnostic_beside_it_fails(self, tmp_path: Path) -> None:
        other = "src/a.ts(1,1): error TS2322: Type 'string' is not assignable to type 'number'."
        assert _tsc_verdict(self._TS2307.format("dompurify") + "\n" + other, "dompurify", tmp_path) != 0

    def test_ts2307_for_a_module_not_added_fails(self, tmp_path: Path) -> None:
        assert _tsc_verdict(self._TS2307.format("lodash"), "dompurify", tmp_path) != 0

    def test_ts2307_for_a_relative_module_fails(self, tmp_path: Path) -> None:
        assert _tsc_verdict(self._TS2307.format("./missing"), "dompurify", tmp_path) != 0

    def test_a_ts2307_quoted_inside_another_diagnostic_fails(self, tmp_path: Path) -> None:
        """CodeRabbit on #19272: only the diagnostic's own code counts, not a TS2307 quoted in a message."""
        line = (
            "src/a.ts(4,7): error TS2322: Type '\"error TS2307: Cannot find module 'dompurify'\"' "
            "is not assignable to type 'number'."
        )
        assert _tsc_verdict(line, "dompurify", tmp_path) != 0

    _COLON = (
        "src/utils/sanitize.ts:12:23 - error TS2307: Cannot find module '{0}' or its corresponding type declarations."
    )

    def test_the_colon_position_format_for_the_absent_new_dep_defers(self, tmp_path: Path) -> None:
        """CodeRabbit on #19286: vue-tsc's `file:line:col - error` form defers like the parenthesised one."""
        assert _tsc_verdict(self._COLON.format("dompurify"), "dompurify", tmp_path) == 0

    def test_a_ts2307_quoted_inside_a_colon_format_diagnostic_fails(self, tmp_path: Path) -> None:
        line = (
            "src/a.ts:4:7 - error TS2322: Type '\"error TS2307: Cannot find module 'dompurify'\"' "
            "is not assignable to type 'number'."
        )
        assert _tsc_verdict(line, "dompurify", tmp_path) != 0

    def test_a_colon_format_ts2307_for_a_module_not_added_fails(self, tmp_path: Path) -> None:
        assert _tsc_verdict(self._COLON.format("lodash"), "dompurify", tmp_path) != 0

    def test_a_lookalike_package_name_fails(self, tmp_path: Path) -> None:
        assert _tsc_verdict(self._TS2307.format("dompurify-extra"), "dompurify", tmp_path) != 0

    def test_a_scoped_new_dep_defers(self, tmp_path: Path) -> None:
        assert _tsc_verdict(self._TS2307.format("@scope/pkg/sub"), "@scope/pkg", tmp_path) == 0

    def test_coloured_ts2307_fails_closed(self, tmp_path: Path) -> None:
        coloured = self._TS2307.format("dompurify").replace("error", "\x1b[91merror\x1b[0m")
        assert _tsc_verdict(coloured, "dompurify", tmp_path) != 0

    def test_no_diagnostics_is_not_a_deferral(self, tmp_path: Path) -> None:
        assert _tsc_verdict("", "dompurify", tmp_path) != 0

    def test_the_vue_tsc_branch_is_guarded_and_still_fails_otherwise(self) -> None:
        guard = (
            'if [ -n "$relevant" ] && new_dep_absent=$(absent_added_deps "${base:-$remote_sha}" "$local_sha" "$project_dir") \\\n'
            '             && tsc_failed_on_new_dep_only "$relevant" "$new_dep_absent"; then\n'
            "            # It ran: show exactly which diagnostics are being set aside, never a bare skip.\n"
            '            echo "$relevant" | head -20 >&2\n'
            '            could_not_run "vue-tsc (${project})" \\\n'
            '              "ran; only TS2307 for the new dependency (CI\'s npm ci verifies): $(echo $new_dep_absent)"'
        )
        assert guard in _SOURCE
        after = _SOURCE.find(guard)
        assert _SOURCE.find('elif [ -n "$relevant" ]; then', after) > after
        assert _SOURCE.count('tsc_failed_on_new_dep_only "$') == 2  # + the #19472 stale-install elif


def _stale_repo(tmp_path: Path, *, app: dict, kit: dict) -> Path:
    """A committed repo with app/ and libs/autobot-ui/ manifests and the staged tool (#19472)."""
    make_repo(tmp_path)
    for rel, manifest in (("app", app), ("libs/autobot-ui", kit)):
        (tmp_path / rel).mkdir(parents=True)
        (tmp_path / rel / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "app" / "node_modules").mkdir()
    _stage_tool(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


_STALE_BLOCK = re.search(
    r'\n(    stale_deps=""\n(?:.*\n)*?    \[ -n "\$stale_deps" \] && warn "\$stale_reason"\n)', _SOURCE
)


def _stale(root: Path, base: str, head: str, then: str = "", allow: str = "0") -> subprocess.CompletedProcess[str]:
    """The hook's own per-project stale detection for project `app`, followed by `then`."""
    assert _STALE_BLOCK, "the hook no longer carries the #19472 stale block — move this test with it"
    script = "\n".join(
        [
            f"REPO_ROOT={root}; PYTEST_PYTHON={sys.executable}; KIT_TREE=libs/autobot-ui; project=app",
            f'RED=; CLR=; EXIT_CODE=0; ALLOW_UNRUNNABLE={allow}; base={base}; local_sha={head}; project_dir="$REPO_ROOT/app"',
            'warn() { echo "WARN $*" >&2; }',
            *(_fn(name) for name in ("could_not_run", "node_modules_usable", "absent_added_deps")),
            _fn("stale_installed_deps"),
            _fn("vitest_failed_on_new_dep_only"),
            _STALE_BLOCK.group(1),
            'echo "stale=[$(echo $stale_deps)]"',
            then,
            'echo "exit=$EXIT_CODE"',
        ]
    )
    return subprocess.run(
        ["bash", "-c", script], cwd=root, capture_output=True, text=True, check=False, env=isolated_git_env()
    )


#: The vitest branch's stale classification, as the hook writes it (asserted against the source below).
_CLASSIFY = (
    'new_dep_absent=""; out="$(cat out.txt)"\n'
    'if [ -n "$stale_deps" ] && vitest_failed_on_new_dep_only "$out" "$stale_deps $new_dep_absent"; then\n'
    '  could_not_run "vitest (${project})" "$stale_reason"\nelse echo BLAMED; fi'
)


class TestAStaleInstallIsCouldNotRun:
    """#19472: a dependency declared at the base but missing from the linked install."""

    _APP = {"dependencies": {"vue": "1", "dompurify": "3"}, "devDependencies": {"vitest": "5"}}
    _KIT = {"peerDependencies": {"dompurify": ">=3", "vue": ">=3"}, "devDependencies": {"kit-only": "1"}}
    _REASON = "app/node_modules is stale — missing dompurify; the owner refreshes it with: npm ci (in app)"

    def _run(self, tmp_path: Path, output: str, *installed: str, allow: str = "0") -> subprocess.CompletedProcess:
        root = _stale_repo(tmp_path, app=self._APP, kit=self._KIT)
        _install(root, *installed)
        (root / "out.txt").write_text(output, encoding="utf-8")
        head = _git(root, "rev-parse", "HEAD")
        return _stale(root, head, head, then=_CLASSIFY, allow=allow)

    def test_unresolved_stale_import_is_could_not_run_with_one_named_reason(self, tmp_path: Path) -> None:
        done = self._run(tmp_path, _UNRESOLVED, "vue", "vitest")
        assert "stale=[dompurify]" in done.stdout and "exit=1" in done.stdout
        assert "BLAMED" not in done.stdout, "the suites failing on the stale import must not be blamed"
        assert f"WARN {self._REASON}" in done.stderr
        assert [ln for ln in done.stderr.splitlines() if "reason:" in ln] == [
            f"[pre-push COULD NOT RUN]   reason: {self._REASON}"
        ]
        assert str(tmp_path) not in done.stderr

    def test_allow_unrunnable_lets_the_push_proceed(self, tmp_path: Path) -> None:
        done = self._run(tmp_path, _UNRESOLVED, "vue", "vitest", allow="1")
        assert "exit=0" in done.stdout and "BLAMED" not in done.stdout

    def test_a_real_failure_beside_the_stale_import_is_still_blamed(self, tmp_path: Path) -> None:
        done = self._run(tmp_path, _UNRESOLVED + _ASSERTION, "vue", "vitest")
        assert "BLAMED" in done.stdout

    def test_a_non_stale_import_error_is_not_reclassified(self, tmp_path: Path) -> None:
        # dompurify IS stale, but the failed file cannot resolve lodash: that failure is the change's.
        done = self._run(tmp_path, _collect_error("src/a.test.ts", "lodash"), "vue", "vitest")
        assert "stale=[dompurify]" in done.stdout and "BLAMED" in done.stdout
        assert "COULD NOT RUN" not in done.stderr

    def test_a_complete_install_is_not_stale(self, tmp_path: Path) -> None:
        done = self._run(tmp_path, _UNRESOLVED, "vue", "vitest", "dompurify")
        assert "stale=[]" in done.stdout and "BLAMED" in done.stdout
        assert "stale —" not in done.stderr

    def test_kit_peers_count_but_kit_dev_and_optional_peers_do_not(self, tmp_path: Path) -> None:
        kit = dict(self._KIT, peerDependenciesMeta={"vue": {"optional": True}})
        root = _stale_repo(tmp_path, app={"dependencies": {}}, kit=kit)
        head = _git(root, "rev-parse", "HEAD")
        assert "stale=[dompurify]" in _stale(root, head, head).stdout

    def test_an_optional_peer_that_is_also_a_direct_dependency_still_counts(self, tmp_path: Path) -> None:
        app = {
            "dependencies": {"foo": "1"},
            "peerDependencies": {"foo": "1", "bar": "1"},
            "peerDependenciesMeta": {"foo": {"optional": True}, "bar": {"optional": True}},
        }
        root = _stale_repo(tmp_path, app=app, kit={})
        head = _git(root, "rev-parse", "HEAD")
        assert "stale=[foo]" in _stale(root, head, head).stdout, "bar is only an optional peer; foo is direct"

    def test_a_dependency_the_push_adds_stays_with_the_19130_classifier(self, tmp_path: Path) -> None:
        root, base, head = _repo(tmp_path)
        _stage_tool(root)
        _install(root, "vue")
        assert "stale=[]" in _stale(root, base, head).stdout

    def test_each_run_branch_classifies_a_stale_install_before_blaming(self) -> None:
        for out_var, label, blame in (
            ("vitest_output", "vitest (${project})", 'fail "vitest failures (${project}'),
            ("kit_output", "vitest related (${project})", 'fail "vitest failures after'),
        ):
            guard = (
                f'&& vitest_failed_on_new_dep_only "${out_var}" "$stale_deps $new_dep_absent"; then\n'
                f'        could_not_run "{label}" "$stale_reason"\n'
            )
            assert _SOURCE.count(guard) == 1, label
            assert _SOURCE.find(guard) < _SOURCE.find(blame, _SOURCE.find(guard))
        tsc = '&& tsc_failed_on_new_dep_only "$relevant" "$stale_deps $new_dep_absent"; then'
        assert _SOURCE.find(tsc) < _SOURCE.find('fail "vue-tsc errors in CHANGED files') and tsc in _SOURCE
        assert _SOURCE.find(_STALE_BLOCK.group(1)) < _SOURCE.find("npm run --silent type-check")
