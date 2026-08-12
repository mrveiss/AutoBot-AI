#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_git_safe_directory (#7219)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_git_safe_directory import find_violations  # noqa: E402


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_unguarded_blocked() -> None:
    body = "      command: git -C {{ git_repo_root }} log -1 --format='%h %s'\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_passes() -> None:
    body = "      command: git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }} log -1\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_unguarded_literal_path_blocked() -> None:
    body = "      cmd: git -C /opt/autobot/code_source status --porcelain\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_literal_path_passes() -> None:
    body = "      cmd: git -c safe.directory=/opt/autobot/code_source -C /opt/autobot/code_source status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_git_other_dir_unaffected() -> None:
    """git -C of an UNrelated dir doesn't trigger the check."""
    body = "      cmd: git -C /tmp/some_repo log\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_multiline_play_with_guard_passes() -> None:
    body = (
        "      cmd: >-\n"
        "        git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }}\n"
        "        log -1 --format='%h %s'\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        # Single-line-only check; multi-line >- folded form should be on one line by the time YAML parses it.
        # Per-line check: the line containing `git -C` must have `-c safe.directory` on the SAME line.
        # In the above sample, both are on the same line — should pass.
        assert find_violations(f) == []


if __name__ == "__main__":
    test_unguarded_blocked()
    test_guarded_passes()
    test_unguarded_literal_path_blocked()
    test_guarded_literal_path_passes()
    test_git_other_dir_unaffected()
    test_multiline_play_with_guard_passes()
    print("All tests passed.")


# --- #14181: the pattern was blind to every Jinja name but `git_repo_root` ----


def test_an_alternately_named_code_source_var_is_blocked() -> None:
    """`{{ _code_source_dest }}` is the same directory under a different name.

    The original target group accepted only the literal `{{ git_repo_root }}`
    or the literal path, so three real unguarded sites in the update/deploy
    path passed the rule — which is precisely where a `dubious ownership`
    rc=128 aborts a deploy (#7150).
    """
    body = "        cmd: \"git -C {{ _code_source_dest }} log -1 --format='%h %s'\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "alt.yml", body)
        assert len(find_violations(f)) == 1


def test_a_filtered_code_source_var_is_blocked() -> None:
    """A Jinja filter expression must not hide the target either."""
    body = "          git -C {{ code_source_dir | default('/opt/autobot/code_source') }} rev-parse HEAD\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "filtered.yml", body)
        assert len(find_violations(f)) == 1


def test_the_same_alternately_named_vars_pass_once_guarded() -> None:
    """Widening must not make the guarded form unrecognisable.

    A widened matcher that flagged correctly-guarded lines would be worse than
    the blind one — it would block every site #7150 already fixed.
    """
    bodies = [
        "        cmd: \"git -c safe.directory={{ _code_source_dest }} -C {{ _code_source_dest }} log -1\"\n",
        "          git -c safe.directory={{ code_source_dir | default('/opt/autobot/code_source') }}\n"
        "          -C {{ code_source_dir | default('/opt/autobot/code_source') }} rev-parse HEAD\n",
    ]
    with tempfile.TemporaryDirectory() as d:
        for index, body in enumerate(bodies):
            f = _write(Path(d), f"guarded{index}.yml", body)
            assert find_violations(f) == [], body


def test_an_unrelated_git_c_is_still_ignored() -> None:
    """The widening keys on the *name*, not on `-C` alone."""
    body = "      command: git -C {{ some_other_dir }} status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "unrelated.yml", body)
        assert find_violations(f) == []


def test_a_command_split_across_lines_is_not_silently_invisible() -> None:
    """A guard the checker cannot see is not a guard.

    Found on this PR: guarding two sites pushed `git ... -C ...` onto two
    physical lines of a `>-` folded scalar. The command was correct, but both
    patterns are line-based — `git` was on one line and `-C` on the next — so
    the checker stopped matching them entirely. They read as fixed while being
    unwatched, and a later edit removing `safe.directory` would not be caught.

    This pins the shape rather than the instance: a `git` line with no `-C`
    must not be treated as a passing guarded site, because it is not a site at
    all. The real protection is that the fixed files keep their commands on one
    line, which `test_the_repository_guarded_sites_stay_visible` asserts.
    """
    body = (
        "        cmd: >-\n"
        "          git -c safe.directory={{ git_repo_root }}\n"
        "          -C {{ git_repo_root }} rev-parse HEAD\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "split.yml", body)
        # Neither line matches: no violation is reported, and that is precisely
        # the blind spot — asserted so the behaviour is documented, not assumed.
        assert find_violations(f) == []


def test_the_repository_guarded_sites_stay_visible() -> None:
    """Every real `git -C <code_source>` in the tree is on one line and guarded.

    This is the assertion that would have caught the split introduced on this
    PR. It runs against the actual repository rather than a fixture, so it
    fails if any future edit folds a guarded command across lines and quietly
    removes it from the checker's view.
    """
    import subprocess  # nosec B404  # git plumbing, fixed argv, no shell

    from check_git_safe_directory import PATTERN, REPO_ROOT, SAFE_FLAG

    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.yml", "*.yaml"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert listing.returncode == 0, "git ls-files failed — refusing to report clean"
    tracked = listing.stdout.split()
    assert tracked, "git ls-files listed nothing — refusing to report clean"

    visible = 0
    for name in tracked:
        path = REPO_ROOT / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if PATTERN.search(line):
                visible += 1
                assert SAFE_FLAG.search(line) or name.endswith(".pre-commit-config.yaml"), (
                    f"{name}: an unguarded `git -C <code_source>` is visible to the checker:\n  {line.strip()[:120]}"
                )

    # Two weaker forms were tried and both let the mutation through, so they
    # are recorded rather than repeated: a `visible >= 20` floor still passed
    # when re-splitting one site dropped the count to 20, and "each file has at
    # least one visible site" still passed because update-all-nodes.yml has ten
    # other guarded sites. The assertion has to name the *specific* command
    # each fix guards.
    must_be_visible = {
        "autobot-slm-backend/ansible/playbooks/sync-code-source.yml": "_code_source_dest",
        # Marker must be UNIQUE to the guarded site. "rev-parse HEAD" is not:
        # update-all-nodes.yml:150 contains "rev-parse HEAD~", which matches as a
        # substring, so re-splitting line 274 still found a "matching" line and the
        # mutation passed. "code_source_dir" appears only on the sites this fix
        # guards; the other ten use git_repo_root.
        "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml": "code_source_dir",
        "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml": "code_source_dir",
    }
    for name, marker in sorted(must_be_visible.items()):
        path = REPO_ROOT / name
        if not path.is_file():  # pragma: no cover - file moved
            continue
        hits = [line for line in path.read_text(encoding="utf-8").splitlines() if PATTERN.search(line)]
        matching = [line for line in hits if marker in line]
        assert matching, (
            f"{name}: the `{marker}` command is no longer visible to the checker. "
            "A guarded command folded across physical lines drops out of view entirely — "
            "the command stays correct while the guard stops watching it."
        )
        assert all(SAFE_FLAG.search(line) for line in matching), f"{name}: `{marker}` lost its safe.directory guard"

    assert visible >= len(must_be_visible), f"expected at least {len(must_be_visible)} visible sites, found {visible}"
