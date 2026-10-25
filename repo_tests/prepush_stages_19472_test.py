#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""pre-push stages run in parallel, a pass is cached by content, and train-* runs the guard set (#19472).

The stage helpers are the hook's OWN functions, extracted verbatim and driven in a throwaway
repo; train mode is driven through the whole hook. A reimplementation here would agree with
itself and prove nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_SOURCE = _HOOK.read_text(encoding="utf-8")
_STAGE_FNS = (
    "did_not_run",
    "could_not_run",
    "stage_cache_dir",
    "stage_key",
    "stage_marker",
    "stage_cached",
    "stage_begin",
    "stage_exit",
    "stage_track",
    "stage_wait_all",
    "stage_record",
    "stage_cache_usable",
    "train_mode_ref",
)
_STUBS = (
    "RED=; CLR=; EXIT_CODE=0; ALLOW_UNRUNNABLE=0; ALLOW_TIMEOUT=0; STAGE_CLEAN=1\n"
    "STAGE_PIDS=(); STAGE_LOGS=(); STAGE_NAMES=(); STAGE_KEYS=()\n"
    'ok() { echo "OK $*" >&2; }; fail() { echo "FAIL $*" >&2; }; warn() { echo "WARN $*" >&2; }\n'
)


def _fn(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n(?:.*\n)*?\}}$", _SOURCE, re.MULTILINE)
    assert match, f"the hook no longer defines {name} — move this test with it, do not delete it"
    return match.group(0)


def _stage(name: str, body: str) -> str:
    """One stage, shaped exactly as the hook launches one."""
    return (
        f'key=$(stage_key "{name}" src)\n'
        f'if ! stage_cached "{name}" "$key"; then\n'
        f'stage_begin "{name}" "$key"\n'
        f'( EXIT_CODE=0; STAGE_CLEAN=1\n{body}\nstage_exit ) </dev/null >"$STAGE_LOG" 2>&1 &\n'
        "stage_track $!\nfi\n"
    )


def _run(repo: Path, *stages: str, sha: str = "", **env: str) -> subprocess.CompletedProcess[str]:
    """The stages against `sha` (default HEAD), the cache decided as the hook decides it."""
    head = sha or git(repo, "rev-parse", "HEAD").stdout.strip()
    script = "\n".join(
        [
            _STUBS,
            f"local_sha={head}",
            *(_fn(n) for n in _STAGE_FNS),
            "STAGE_CACHE_OK=0; stage_cache_usable && STAGE_CACHE_OK=1",
            *stages,
            "stage_wait_all",
            'echo "exit=$EXIT_CODE"',
        ]
    )
    full_env = {**isolated_git_env(), **env}
    return subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True, check=False, env=full_env)


def _repo(tmp_path: Path, content: str = "one") -> Path:
    repo = make_repo(tmp_path / "repo")
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "a.txt").write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", content)
    return repo


_PASS = _stage("A", 'echo A1 >&2; sleep 0.3; echo A2 >&2; ok "A"')
_FAIL = _stage("B", 'echo B1 >&2; sleep 0.1; echo B2 >&2; fail "B"; EXIT_CODE=1')
_UNRUNNABLE = _stage("C", 'ALLOW_UNRUNNABLE=1; could_not_run "C" "no install"')


class TestParallelStages:
    def test_one_failing_stage_blocks_the_push(self, tmp_path: Path) -> None:
        done = _run(_repo(tmp_path), _PASS, _FAIL)
        assert "exit=1" in done.stdout

    def test_all_passing_stages_pass(self, tmp_path: Path) -> None:
        done = _run(_repo(tmp_path), _PASS, _stage("D", 'ok "D"'))
        assert "exit=0" in done.stdout

    def test_each_stage_prints_as_one_block(self, tmp_path: Path) -> None:
        lines = _run(_repo(tmp_path), _PASS, _FAIL).stderr.splitlines()
        assert lines[lines.index("A1") + 1] == "A2"
        assert lines[lines.index("B1") + 1] == "B2"

    def test_a_stage_failure_survives_an_earlier_parent_failure_reset(self, tmp_path: Path) -> None:
        # The subshell resets EXIT_CODE; the parent's own earlier failure must still stand.
        done = _run(_repo(tmp_path), "EXIT_CODE=1", _PASS)
        assert "exit=1" in done.stdout

    def test_serial_mode_reaches_the_same_verdict(self, tmp_path: Path) -> None:
        done = _run(_repo(tmp_path), _PASS, _FAIL, AUTOBOT_PREPUSH_PARALLEL="0")
        assert "exit=1" in done.stdout

    def test_an_allowed_could_not_run_does_not_block(self, tmp_path: Path) -> None:
        assert "exit=0" in _run(_repo(tmp_path), _UNRUNNABLE).stdout


def _markers(repo: Path) -> list[Path]:
    return sorted((repo / ".git" / "autobot-prepush-cache").glob("*"))


class TestContentKeyedPassCache:
    def test_a_pass_is_recorded_under_the_git_dir_and_a_hit_skips(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert "OK A" in _run(repo, _PASS).stderr
        assert len(_markers(repo)) == 1
        assert git(repo, "status", "--porcelain").stdout == "", "the cache must never land in the tree"
        again = _run(repo, _PASS)
        assert "A1" not in again.stderr
        assert re.search(r"OK A: unchanged since a recorded pass @ [0-9a-f]{10}, skipped", again.stderr)

    def test_a_changed_input_runs_again(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _run(repo, _PASS)
        (repo / "src" / "a.txt").write_text("two", encoding="utf-8")
        git(repo, "commit", "-qam", "two")
        assert "A1" in _run(repo, _PASS).stderr

    def test_a_fail_is_never_cached(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _run(repo, _FAIL)
        assert _markers(repo) == []
        assert "B1" in _run(repo, _FAIL).stderr

    def test_an_allowed_could_not_run_is_never_cached(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _run(repo, _UNRUNNABLE)
        assert _markers(repo) == []

    def test_a_dirty_tree_neither_writes_nor_uses_the_cache(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        (repo / "src" / "scratch.txt").write_text("untracked", encoding="utf-8")
        _run(repo, _PASS)
        assert _markers(repo) == [], "a pass on a dirty tree describes no commit"
        (repo / "src" / "scratch.txt").unlink()
        _run(repo, _PASS)
        assert len(_markers(repo)) == 1
        (repo / "src" / "a.txt").write_text("edited", encoding="utf-8")
        assert "A1" in _run(repo, _PASS).stderr, "a recorded pass must not answer for a modified tree"

    def test_a_head_other_than_the_pushed_sha_does_not_use_the_cache(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _run(repo, _PASS)
        pushed = git(repo, "rev-parse", "HEAD").stdout.strip()
        (repo / "src" / "b.txt").write_text("b", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "later")
        assert "A1" in _run(repo, _PASS, sha=pushed).stderr

    def test_a_docs_change_invalidates_the_pytest_key(self, tmp_path: Path) -> None:
        assert 'pytest_key=$(stage_key "pytest|${PYTEST_PYTHON}|${selection}" "")' in _SOURCE
        repo = _repo(tmp_path)
        key = 'stage_key "pytest|py|sel" ""'
        first = _run(repo, f'echo "key=$({key})"').stdout
        (repo / "docs").mkdir()
        (repo / "docs" / "x.md").write_text("doc", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "docs")
        assert first != _run(repo, f'echo "key=$({key})"').stdout

    def test_a_frontend_key_follows_the_install_and_is_empty_without_one(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        lock = repo / "app" / "node_modules" / ".package-lock.json"
        probe = (
            f"{_fn('fe_key')}\nproject_dir={repo}/app\n"
            'fe_install=$(sha256sum "$project_dir/node_modules/.package-lock.json" 2>/dev/null | cut -c1-64)\n'
            'fe_env="install=${fe_install}"; key=$(fe_key vitest sel); echo "key=[$key]"\n'
            'stage_cached vitest "$key" || echo MISS'
        )
        assert "key=[]" in _run(repo, probe).stdout and "MISS" in _run(repo, probe).stdout
        lock.parent.mkdir(parents=True)
        lock.write_text('{"v": 1}', encoding="utf-8")
        first = _run(repo, probe).stdout
        lock.write_text('{"v": 2}', encoding="utf-8")
        assert "key=[]" not in first and first != _run(repo, probe).stdout

    def test_a_change_in_any_tree_changes_the_frontend_key(self, tmp_path: Path) -> None:
        assert "fe_reach_trees" not in _SOURCE, "the config parse failed open; the whole tree is the key"
        repo = _repo(tmp_path)
        probe = f"{_fn('fe_key')}\nfe_install=x; fe_env=e\n" 'echo "key=$(fe_key vitest sel)"'
        before = _run(repo, probe).stdout
        for tree in ("unrelated", "docs", "app"):
            (repo / tree).mkdir(exist_ok=True)
            (repo / tree / "z.ts").write_text(tree, encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", tree)
            after = _run(repo, probe).stdout
            assert after != before, tree
            before = after

    def test_the_cache_can_be_switched_off(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _run(repo, _PASS)
        assert "A1" in _run(repo, _PASS, AUTOBOT_PREPUSH_CACHE="0").stderr

    def test_every_heavy_run_is_a_stage(self) -> None:
        for name in ("vue-tsc ${project}", "vitest ${project}", "vitest related ${project}", "pytest", "train guards"):
            assert f'stage_begin "{name}"' in _SOURCE, name
        assert _SOURCE.count("stage_exit\n") >= 4
        assert "  stage_wait_all\ndone\n" in _SOURCE, "every ref's stages are collected before the next ref"


_GUARDS = re.search(r"train_guard_tests\(\) \{\n  cat <<'EOF'\n((?:.*\n)*?)EOF\n\}", _SOURCE)


def _guard_list() -> list[str]:
    assert _GUARDS, "the hook no longer lists the train guards — move this test with it"
    return [line for line in _GUARDS.group(1).splitlines() if line]


def _shim(tmp_path: Path) -> str:
    """`python3` -> this interpreter (it has pytest); `gh` -> a no-PR answer, never the network."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shims = {
        "python3": f'#!/bin/sh\nexec "{sys.executable}" "$@"\n',
        "gh": "#!/bin/sh\necho 'no pull requests found for branch' >&2\nexit 1\n",
    }
    for name, text in shims.items():
        (bin_dir / name).write_text(text, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


#: Train shapes: what lands on the train's first-parent line after the base.
_SHAPES = {
    "member": ("merge member",),
    "plain": ("plain",),
    "member+fix": ("merge member", "fix(train): train-x repair"),
    "member+plain": ("merge member", "plain"),
    "main+plain": ("merge main", "plain"),
    "main+fix": ("merge main", "fix(train): train-x repair"),
}


def _commit(repo: Path, name: str, message: str) -> None:
    (repo / name).write_text(f"{message}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


def _train_repo(tmp_path: Path, shape: str = "member") -> tuple[Path, str, str]:
    """base on main, then a `train` branch shaped per _SHAPES. Returns (repo, merge base with main, head)."""
    repo = make_repo(tmp_path / "repo")
    for guard in _guard_list():
        (repo / guard).parent.mkdir(parents=True, exist_ok=True)
        (repo / guard).write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (repo / "scripts" / "repin_reach_floors.py").write_text("print('OK nothing stale')\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    main = git(repo, "branch", "--show-current").stdout.strip()
    git(repo, "switch", "-qc", "member")
    _commit(repo, "mod.py", "member work")
    git(repo, "switch", "-q", main)
    _commit(repo, "main.txt", "main moves on")
    git(repo, "switch", "-qc", "train", "HEAD~1")
    for step in _SHAPES[shape]:
        if step.startswith("merge "):
            git(repo, "merge", "-q", "--no-ff", "-m", step, main if step == "merge main" else "member")
        else:
            _commit(repo, f"{len(step)}.txt", step)
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, git(repo, "merge-base", head, main).stdout.strip(), head


def _push(tmp_path: Path, local: str, remote: str, *, shape: str = "member") -> subprocess.CompletedProcess[str]:
    repo, base, head = _train_repo(tmp_path, shape)
    env = {**isolated_git_env(), "PATH": _shim(tmp_path), "AUTOBOT_PREPUSH_CACHE": "0"}
    return subprocess.run(
        ["bash", str(_HOOK)],
        input=f"refs/heads/{local} {head} refs/heads/{remote} {base}\n",
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=300,
    )


def _guards(tmp_path: Path, *, guard: str = "pass", repin: str = "print('OK')") -> subprocess.CompletedProcess[str]:
    """The hook's own run_train_guards; `timeout` answers 124 for a repin given `raise TimeoutError`."""
    repo, _, _ = _train_repo(tmp_path)
    (repo / _guard_list()[0]).write_text(f"def test_x():\n    {guard}\n", encoding="utf-8")
    (repo / "scripts" / "repin_reach_floors.py").write_text(repin + "\n", encoding="utf-8")
    script = "\n".join(
        [
            _STUBS,
            f"REPO_ROOT={repo}; PYTEST_PYTHON={sys.executable}; MAX_BUDGET=60",
            "pytest_xdist_args() { :; }; failure_excerpt() { printf '%s\\n' \"$1\" | tail -5; }",
            'timeout() { shift; if [[ "$*" == *repin* ]] && grep -q TimeoutError scripts/repin_reach_floors.py; '
            'then return 124; fi; "$@"; }',
            _fn("did_not_run"),
            _fn("could_not_run"),
            _fn("train_guard_tests"),
            _fn("run_train_guards"),
            "run_train_guards",
            'echo "exit=$EXIT_CODE clean=$STAGE_CLEAN"',
        ]
    )
    return subprocess.run(
        ["bash", "-c", script], cwd=repo, capture_output=True, text=True, check=False, env=isolated_git_env()
    )


class TestTrainMode:
    def test_both_refs_must_be_train_and_the_range_must_hold_a_merge(self, tmp_path: Path) -> None:
        repo, base, head = _train_repo(tmp_path)
        cases = (
            ("refs/heads/train-x", "refs/heads/train-x", base, "train"),
            ("refs/heads/issue-x", "refs/heads/train-x", base, "full"),
            ("refs/heads/train-x", "refs/heads/issue-x", base, "full"),
            ("refs/heads/x-train-y", "refs/heads/x-train-y", base, "full"),
            ("refs/tags/train-x", "refs/tags/train-x", base, "full"),
            ("refs/heads/train-x", "refs/heads/train-x", "", "full"),
        )
        script = f"{_fn('train_mode_ref')}\n{_fn('train_range_ok')}\n" + "".join(
            f'train_mode_ref {lr} {rr} "{b}" {head} && echo train || echo full\n' for lr, rr, b, _ in cases
        )
        out = subprocess.run(
            ["bash", "-c", script], cwd=repo, capture_output=True, text=True, check=False, env=isolated_git_env()
        ).stdout.split()
        assert out == [c[3] for c in cases]

    @staticmethod
    def _mode(tmp_path: Path, shape: str) -> str:
        repo, base, head = _train_repo(tmp_path, shape)
        script = (
            f'{_fn("train_mode_ref")}\n{_fn("train_range_ok")}\n'
            f'train_mode_ref refs/heads/train-x refs/heads/train-x {base} {head} && echo train || echo "full: $TRAIN_OFF"'
        )
        done = subprocess.run(
            ["bash", "-c", script], cwd=repo, capture_output=True, text=True, check=False, env=isolated_git_env()
        )
        return done.stdout.strip()

    def test_a_merged_member_plus_a_fix_train_commit_is_a_train(self, tmp_path: Path) -> None:
        assert self._mode(tmp_path, "member+fix") == "train"

    def test_a_merged_member_plus_an_unprefixed_commit_is_a_full_run(self, tmp_path: Path) -> None:
        assert self._mode(tmp_path, "member+plain").startswith("full: first-parent commit ")

    def test_merge_main_plus_a_plain_commit_is_a_full_run(self, tmp_path: Path) -> None:
        assert self._mode(tmp_path, "main+plain").startswith("full: first-parent commit ")

    def test_merging_only_the_base_branch_is_not_a_train(self, tmp_path: Path) -> None:
        assert self._mode(tmp_path, "main+fix") == "full: no first-parent merge brings in anything but the base branch"

    def test_a_range_with_no_merge_is_not_a_train(self, tmp_path: Path) -> None:
        assert self._mode(tmp_path, "plain").startswith("full: ")

    def test_the_guard_set_is_the_fourteen_preflight_guards_and_each_exists(self) -> None:
        guards = _guard_list()
        assert len(guards) == len(set(guards)) == 14
        assert [g for g in guards if not (repo_root() / g).is_file()] == []
        assert "scripts/repin_reach_floors.py --check" in _SOURCE

    def test_a_train_push_runs_only_the_guard_set(self, tmp_path: Path) -> None:
        done = _push(tmp_path, "train-x", "train-x")
        assert "train mode: train-x runs only the fast guard set" in done.stderr
        assert "train guards: 14 guard file(s) pass" in done.stderr, done.stderr[-3000:]
        assert "pytest selection" not in done.stderr and "pytest selected" not in done.stderr
        assert done.returncode == 0, done.stderr[-3000:]

    def test_an_issue_push_runs_the_full_pre_push(self, tmp_path: Path) -> None:
        done = _push(tmp_path, "issue-x", "issue-x")
        assert "train mode" not in done.stderr
        # The fixture carries no tools/lint, so Phase 0c's selection reports itself; it RAN.
        assert "pytest selection" in done.stderr or "pytest selected" in done.stderr, done.stderr[-3000:]

    def test_an_issue_branch_pushed_to_a_train_ref_runs_the_full_pre_push(self, tmp_path: Path) -> None:
        done = _push(tmp_path, "issue-x", "train-x")
        assert "train mode OFF: the local and the remote ref must both be" in done.stderr
        assert "train guards" not in done.stderr
        assert "pytest selection" in done.stderr or "pytest selected" in done.stderr, done.stderr[-3000:]

    def test_a_failing_train_guard_blocks(self, tmp_path: Path) -> None:
        done = _guards(tmp_path, guard="assert False")
        assert "exit=1" in done.stdout and "FAIL train guards failed" in done.stderr

    def test_a_repin_crash_blocks(self, tmp_path: Path) -> None:
        done = _guards(tmp_path, repin="raise SystemExit(1)")
        assert "exit=1" in done.stdout and "crashed (exit 1)" in done.stderr

    def test_a_repin_exit_2_passes_but_is_never_cached_and_names_the_unmeasured(self, tmp_path: Path) -> None:
        repin = "import sys; print('ERROR: 1 guard module(s) failed to import: g', file=sys.stderr); sys.exit(2)"
        done = _guards(tmp_path, repin=repin)
        # The push passes (exit 0) but the stage is unclean, so stage_exit returns 3: never cached.
        assert "exit=0 clean=0" in done.stdout, done.stderr
        assert (
            "WARN reach floors NOT measured for some guards: ERROR: 1 guard module(s) failed to import: g"
            in done.stderr
        )

    def test_a_repin_exit_1_with_stale_lines_is_stale_not_a_crash(self, tmp_path: Path) -> None:
        done = _guards(tmp_path, repin="print('STALE x'); raise SystemExit(1)")
        assert "reach floors are stale" in done.stderr and "crashed" not in done.stderr

    def test_a_repin_stale_line_blocks(self, tmp_path: Path) -> None:
        done = _guards(tmp_path, repin="print('STALE x')")
        assert "exit=1" in done.stdout and "reach floors are stale" in done.stderr

    def test_a_repin_timeout_is_did_not_run(self, tmp_path: Path) -> None:
        done = _guards(tmp_path, repin="raise TimeoutError")
        assert "exit=1 clean=0" in done.stdout and "DID NOT RUN" in done.stderr
