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

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_git_safe_directory import (  # noqa: E402
    PATTERN,
    REPO_ROOT,
    SAFE_FLAG,
    _iter_scalar_nodes,
    find_violations,
)


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_unguarded_blocked() -> None:
    body = "- name: t\n  command: git -C {{ git_repo_root }} log -1 --format='%h %s'\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_passes() -> None:
    body = "- name: t\n  command: git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }} log -1\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_unguarded_literal_path_blocked() -> None:
    body = "- name: t\n  cmd: git -C /opt/autobot/code_source status --porcelain\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_literal_path_passes() -> None:
    body = "- name: t\n  cmd: git -c safe.directory=/opt/autobot/code_source -C /opt/autobot/code_source status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_git_other_dir_unaffected() -> None:
    """git -C of an UNrelated dir doesn't trigger the check."""
    body = "- name: t\n  cmd: git -C /tmp/some_repo log\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_multiline_play_with_guard_passes() -> None:
    body = (
        "- name: t\n"
        "  cmd: >-\n"
        "    git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }}\n"
        "    log -1 --format='%h %s'\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
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
    body = "- name: t\n  cmd: \"git -C {{ _code_source_dest }} log -1 --format='%h %s'\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "alt.yml", body)
        assert len(find_violations(f)) == 1


def test_a_filtered_code_source_var_is_blocked() -> None:
    """A Jinja filter expression must not hide the target either."""
    body = "- name: t\n  cmd: git -C {{ code_source_dir | default('/opt/autobot/code_source') }} rev-parse HEAD\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "filtered.yml", body)
        assert len(find_violations(f)) == 1


def test_the_same_alternately_named_vars_pass_once_guarded() -> None:
    """Widening must not make the guarded form unrecognisable.

    A widened matcher that flagged correctly-guarded lines would be worse than
    the blind one — it would block every site #7150 already fixed.
    """
    bodies = [
        "- name: t\n  cmd: \"git -c safe.directory={{ _code_source_dest }} -C {{ _code_source_dest }} log -1\"\n",
        "- name: t\n"
        "  cmd: >-\n"
        "    git -c safe.directory={{ code_source_dir | default('/opt/autobot/code_source') }}\n"
        "    -C {{ code_source_dir | default('/opt/autobot/code_source') }} rev-parse HEAD\n",
    ]
    with tempfile.TemporaryDirectory() as d:
        for index, body in enumerate(bodies):
            f = _write(Path(d), f"guarded{index}.yml", body)
            assert find_violations(f) == [], body


def test_an_unrelated_git_c_is_still_ignored() -> None:
    """The widening keys on the *name*, not on `-C` alone."""
    body = "- name: t\n  command: git -C {{ some_other_dir }} status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "unrelated.yml", body)
        assert find_violations(f) == []


# --- #14196: structural parsing sees the value, not the physical line ---------


def test_an_unguarded_command_split_across_lines_is_now_caught() -> None:
    """The line-based version's actual, historical blind spot.

    #14188 guarded two sites and the guarded command no longer fit on one
    physical line of a `>-` folded scalar; `git` landed on one line and `-C`
    on the next, so both patterns being line-based meant the checker stopped
    matching them entirely — a regression removing `safe.directory` later
    would not have been caught. Parsing the YAML and matching the *resolved*
    scalar value (which PyYAML folds into one string regardless of how many
    physical lines it spans) closes this: an UNGUARDED version of the same
    split must now be blocked.
    """
    body = "- name: t\n  cmd: >-\n    git\n    -C {{ git_repo_root }} rev-parse HEAD\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "split_unguarded.yml", body)
        assert len(find_violations(f)) == 1


def test_a_guarded_command_split_across_lines_still_passes() -> None:
    """The same split, but guarded — proves the fix isn't a blanket reject of
    multi-line commands, only of the unguarded ones.
    """
    body = "- name: t\n  cmd: >-\n    git -c safe.directory={{ git_repo_root }}\n    -C {{ git_repo_root }} rev-parse HEAD\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "split_guarded.yml", body)
        assert find_violations(f) == []


def test_literal_block_scalar_command_is_caught() -> None:
    body = "- name: t\n  shell: |\n    git -C /opt/autobot/code_source status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "literal.yml", body)
        assert len(find_violations(f)) == 1


def test_an_unguarded_command_used_as_a_mapping_key_is_caught() -> None:
    """A dynamically-keyed mapping is a contrived shape, but it proves the
    same coverage as the ansible-facts checker's mapping-key fixture: the
    node-walk must yield mapping KEYS as well as values. A walk that only
    descended into `value_node` would silently drop this, even though the
    pre-#14196 line-based scanner (which matched anywhere in a line) caught
    it.
    """
    body = "- name: t\n  vars:\n    \"git -C {{ git_repo_root }} log -1\": marker\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "key_git.yml", body)
        assert len(find_violations(f)) == 1


def test_malformed_yaml_does_not_crash_the_hook() -> None:
    """Broken YAML syntax is another hook's job (check-yaml)."""
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "broken.yml", "cmd: [unclosed\n")
        assert find_violations(f) == []


def test_the_repository_guarded_sites_stay_visible() -> None:
    """Every real `git -C <code_source>` in the tree is visible and guarded.

    This runs against the actual repository rather than a fixture, so it
    fails if a future edit removes `safe.directory` from a real site, or if
    the structural walk itself regresses and stops reaching a site.

    Unlike the line-based era, the guarded commands are no longer required
    to stay on one physical line (#14196 relaxes that constraint from
    #14188) — `sync-code-source.yml`, `update-all-nodes.yml` and
    `slm_manager/tasks/main.yml` now wrap their `git -c safe.directory=...
    -C ...` invocation across several lines of a folded `>-` block, and the
    structural walk still sees it.
    """
    import subprocess  # nosec B404  # git plumbing, fixed argv, no shell

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
        try:
            documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        except yaml.YAMLError:
            continue
        for doc in documents:
            if doc is None:
                continue
            for node in _iter_scalar_nodes(doc):
                match = PATTERN.search(node.value)
                if match is None:
                    continue
                visible += 1
                guarded = SAFE_FLAG.search(match.group("flags"))
                assert guarded or name.endswith(".pre-commit-config.yaml"), (
                    f"{name}: an unguarded `git -C <code_source>` is visible to the checker:\n"
                    f"  {node.value.strip()[:160]}"
                )

    # Marker must be UNIQUE to the guarded site, and matched against the
    # resolved scalar *value* (so it still matches after the command wraps
    # across several physical lines, unlike a per-line marker search).
    must_be_visible = {
        "autobot-slm-backend/ansible/playbooks/sync-code-source.yml": "_code_source_dest",
        "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml": "code_source_dir",
        "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml": "code_source_dir",
    }
    for name, marker in sorted(must_be_visible.items()):
        path = REPO_ROOT / name
        if not path.is_file():  # pragma: no cover - file moved
            continue
        text = path.read_text(encoding="utf-8")
        docs = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        matching = []
        for doc in docs:
            if doc is None:
                continue
            for node in _iter_scalar_nodes(doc):
                if PATTERN.search(node.value) and marker in node.value:
                    matching.append(node.value)
        assert matching, (
            f"{name}: the `{marker}` command is no longer visible to the checker — "
            "a guarded command folded across physical lines dropping out of view "
            "entirely is exactly what #14196 fixed."
        )
        for value in matching:
            match = PATTERN.search(value)
            assert match and SAFE_FLAG.search(match.group("flags")), f"{name}: `{marker}` lost its safe.directory guard"

    assert visible >= len(must_be_visible), f"expected at least {len(must_be_visible)} visible sites, found {visible}"


# --- reach self-check: prove the walk actually descends into the tree ---------


def _tracked_yaml_files() -> list:
    import subprocess  # nosec B404

    listing = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.yml", "*.yaml"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return listing.stdout.split()


def _independent_pattern_match_count() -> int:
    """Count `PATTERN` matches by walking `yaml.safe_load`'s plain dict/list
    output — deliberately NOT the checker's `yaml.compose` node-walk — so a
    regression in that walk cannot also hide from this count.
    """

    def strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for value in obj.values():
                yield from strings(value)
        elif isinstance(obj, list):
            for item in obj:
                yield from strings(item)

    total = 0
    for name in _tracked_yaml_files():
        path = REPO_ROOT / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if doc is None:
                continue
            for value in strings(doc):
                if PATTERN.search(value):
                    total += 1
    return total


def _node_walk_pattern_match_count() -> int:
    total = 0
    for name in _tracked_yaml_files():
        path = REPO_ROOT / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            docs = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if doc is None:
                continue
            for node in _iter_scalar_nodes(doc):
                if PATTERN.search(node.value):
                    total += 1
    return total


def test_the_node_walk_reaches_the_same_matches_as_an_independent_count() -> None:
    """Same principle as the ansible-facts checker's reach test: two
    independently-written traversals (compose-node-walk vs.
    safe_load-dict-recursion) of the same tracked tree must agree on how
    many `git -C <code_source>` sites exist. If the node-walk regressed to
    matching nothing (or matching only some), this would diverge.

    Scope: this proves TRAVERSAL completeness, not CLASSIFICATION
    correctness. Both counters import the same `PATTERN` to decide what
    counts as a match — narrow or widen `PATTERN` and both counters move
    together and stay equal, because they agree on what to look for, not on
    whether the walk actually visits everything reachable.
    """
    walked = _node_walk_pattern_match_count()
    independent = _independent_pattern_match_count()
    assert walked > 0, "the node-walk found zero matches — it never reached the tree"
    assert independent > 0, "the independent count found zero — the ground truth itself is broken"
    assert walked == independent, (
        f"node-walk saw {walked} matches, the independently-counted dict/list "
        f"recursion found {independent} — the two traversals disagree"
    )
