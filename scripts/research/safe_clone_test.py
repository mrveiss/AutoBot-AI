# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the safe-clone helper (#16488).

Every fixture is built at run time under pytest's ``tmp_path`` -- there is no
canned "planted repo" checked in, because a fixture illustrating a hidden-
payload or a hostile ``.git/config`` is exactly the shape this repo's own
whole-tree guards scan for. Building it in-memory/at-runtime keeps the
banned pattern out of the tree entirely.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from repo_tests._paths import repo_root  # noqa: E402
from safe_clone import (  # noqa: E402
    AGENT_INSTRUCTION_NAMES,
    SAFE_CLONE_CONFIG,
    build_clone_command,
    cache_dir_for,
    default_cache_root,
    neutralize,
    scan_hidden_payloads,
    strip_hidden_payloads,
)

# ── build_clone_command ──────────────────────────────────────────────────


def test_build_clone_command_includes_every_safe_flag():
    cmd = build_clone_command("https://example.com/o/r.git", Path("/cache/dest"))
    for setting in SAFE_CLONE_CONFIG:
        assert setting in cmd, f"missing safe setting: {setting}"
    assert "--depth" in cmd
    assert cmd[cmd.index("--depth") + 1] == "1"
    assert "--no-tags" in cmd
    assert "--single-branch" in cmd


def test_build_clone_command_never_recurses_submodules():
    cmd = build_clone_command("https://example.com/o/r.git", Path("/cache/dest"))
    assert "--recurse-submodules" not in cmd
    assert not any("submodule" in part for part in cmd)


def test_build_clone_command_passes_the_url_and_dest():
    dest = Path("/cache/dest")
    cmd = build_clone_command("https://example.com/o/r.git", dest)
    assert cmd[-2:] == ["https://example.com/o/r.git", str(dest)]


def test_build_clone_command_accepts_an_explicit_ref():
    cmd = build_clone_command("https://example.com/o/r.git", Path("/cache/dest"), ref="release")
    assert "--branch" in cmd
    assert cmd[cmd.index("--branch") + 1] == "release"


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file:///etc/passwd",
        "ext::sh -c id",
        "/local/path",
        "git@example.invalid:o/r.git",
    ],
)
def test_build_clone_command_rejects_non_http_schemes(unsafe_url):
    with pytest.raises(ValueError):
        build_clone_command(unsafe_url, Path("/cache/dest"))


# ── cache location ───────────────────────────────────────────────────────


def test_cache_dir_lies_outside_repo_worktrees_and_tmp(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/test-user")
    root = default_cache_root()
    resolved = str(root)

    root_of_repo = str(repo_root())
    assert not resolved.startswith(root_of_repo)
    assert "/.worktrees/" not in resolved
    assert not resolved.startswith("/tmp")
    assert resolved.endswith("/.cache/autobot-research")


def test_cache_dir_honours_xdg_cache_home(monkeypatch, tmp_path):
    custom = tmp_path / "custom-cache-home"
    monkeypatch.setenv("XDG_CACHE_HOME", str(custom))
    root = default_cache_root()
    assert root == custom / "autobot-research"


def test_cache_dir_for_scopes_to_the_identifier(tmp_path):
    d = cache_dir_for("owner__repo__deadbeef", cache_root=tmp_path)
    assert d == tmp_path / "owner__repo__deadbeef"


@pytest.mark.parametrize("unsafe_id", ["../escape", "a/b", "/etc/passwd", ""])
def test_cache_dir_for_rejects_path_traversal_identifiers(unsafe_id, tmp_path):
    with pytest.raises(ValueError):
        cache_dir_for(unsafe_id, cache_root=tmp_path)


# ── neutralize ────────────────────────────────────────────────────────────


def _plant_agent_instruction_files(tree: Path) -> None:
    (tree / "CLAUDE.md").write_text("agent instructions planted here\n", encoding="utf-8")
    (tree / "AGENTS.md").write_text("agent instructions planted here\n", encoding="utf-8")
    (tree / ".mcp.json").write_text("{}\n", encoding="utf-8")
    (tree / ".cursorrules").write_text("rules\n", encoding="utf-8")
    claude_dir = tree / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")


def test_neutralize_renames_every_planted_instruction_file_and_deletes_git(tmp_path):
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    git_dir = tree / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    _plant_agent_instruction_files(tree)

    manifest = neutralize(tree)
    assert manifest, "neutralize reported nothing -- the planted fixtures were not found"

    assert not git_dir.exists()
    assert not (tree / "CLAUDE.md").exists()
    assert (tree / "CLAUDE.md.untrusted").is_file()
    assert not (tree / "AGENTS.md").exists()
    assert (tree / "AGENTS.md.untrusted").is_file()
    assert not (tree / ".mcp.json").exists()
    assert (tree / ".mcp.json.untrusted").is_file()
    assert not (tree / ".cursorrules").exists()
    assert (tree / ".cursorrules.untrusted").is_file()
    assert not (tree / ".claude").exists()
    assert (tree / ".claude.untrusted" / "settings.json").is_file()

    deleted = {e.path for e in manifest if e.action == "deleted"}
    renamed = {e.path for e in manifest if e.action == "renamed"}
    assert ".git" in deleted
    assert {"CLAUDE.md", "AGENTS.md", ".mcp.json", ".cursorrules", ".claude"} <= renamed


def test_neutralize_covers_every_documented_agent_instruction_name(tmp_path):
    # Every name #16488 lists must actually be neutralised, not only the five
    # spot-checked above -- GEMINI.md, CLAUDE.local.md, .cursor/, .windsurfrules
    # and the nested .github form.
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    for name in AGENT_INSTRUCTION_NAMES:
        target = tree / name
        if "/" in name:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("planted\n", encoding="utf-8")
        elif name in (".claude", ".cursor"):
            target.mkdir(parents=True, exist_ok=True)
            (target / "placeholder.txt").write_text("planted\n", encoding="utf-8")
        else:
            target.write_text("planted\n", encoding="utf-8")

    neutralize(tree)

    for name in AGENT_INSTRUCTION_NAMES:
        original = tree / name
        assert not original.exists(), f"{name} was not neutralised"
        untrusted = original.with_name(original.name + ".untrusted")
        assert untrusted.exists(), f"{name} has no .untrusted counterpart"


def test_neutralized_git_worktree_pointer_file_is_also_removed(tmp_path):
    # A worktree's `.git` is a FILE naming the real git dir, not a directory --
    # neutralize must remove that shape too, not only the ordinary directory.
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    (tree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")

    manifest = neutralize(tree)

    assert not (tree / ".git").exists()
    assert any(e.path == ".git" and e.action == "deleted" for e in manifest)


def test_planted_fsmonitor_hook_never_fires_because_neutralize_never_invokes_git(tmp_path):
    # The attack #16488 names: a `.git/config` pointing `core.fsmonitor` at a
    # script. If neutralize ever ran `git status` (or anything else) inside the
    # tree before removing `.git`, git would invoke that hook. It must not --
    # `.git` is removed by a bare filesystem delete, so the config is never
    # read by git at all.
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    git_dir = tree / ".git"
    git_dir.mkdir()

    marker = tmp_path / "fsmonitor-fired.marker"
    hook_script = tmp_path / "fsmonitor-hook.sh"
    hook_script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)
    (git_dir / "config").write_text(
        f"[core]\n\trepositoryformatversion = 0\n\tfsmonitor = {hook_script}\n",
        encoding="utf-8",
    )

    neutralize(tree)

    assert not marker.exists(), "the planted fsmonitor hook fired -- neutralize invoked git in the tree"
    assert not git_dir.exists()


def test_neutralize_does_not_clobber_an_existing_untrusted_file(tmp_path):
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    (tree / "CLAUDE.md").write_text("real\n", encoding="utf-8")
    (tree / "CLAUDE.md.untrusted").write_text("pre-existing\n", encoding="utf-8")

    neutralize(tree)

    # The original is left in place rather than overwriting the collision --
    # a silent clobber would be a second way to lose evidence of the planted file.
    assert (tree / "CLAUDE.md").exists()
    assert (tree / "CLAUDE.md.untrusted").read_text(encoding="utf-8") == "pre-existing\n"


# ── scan_hidden_payloads / strip_hidden_payloads ──────────────────────────


def _payload_fixtures():
    # Built from code points at run time, never as literal characters in this
    # file's source -- an embedded zero-width/bidi/tag character here would be
    # the exact banned pattern this repo's whole-tree guards scan for.
    tag_characters = "".join(chr(0xE0001 + i) for i in range(3))
    zero_width = "".join(chr(cp) for cp in (0x200B, 0x200C, 0x200D))
    bidi_control = "".join(chr(cp) for cp in (0x202E, 0x2066))
    html_comment = "<!-- a hidden instruction, invisible once this markdown renders -->"
    base64_blob = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo" * 10  # well past the threshold
    return tag_characters, zero_width, bidi_control, html_comment, base64_blob


def test_scan_hidden_payloads_detects_each_planted_kind(tmp_path):
    tag_characters, zero_width, bidi_control, html_comment, base64_blob = _payload_fixtures()
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    (tree / "README.md").write_text(
        f"Normal text {tag_characters} more text\n{html_comment}\ntoken: {base64_blob}\n",
        encoding="utf-8",
    )
    (tree / "notes.txt").write_text(
        f"zero-width{zero_width}here and bidi{bidi_control}there\n",
        encoding="utf-8",
    )

    findings = scan_hidden_payloads(tree)
    by_file: dict[str, set[str]] = {}
    for f in findings:
        by_file.setdefault(f.file, set()).add(f.kind)
        assert f.count > 0

    assert by_file["README.md"] >= {"unicode_tag_characters", "html_comment", "base64_blob"}
    assert by_file["notes.txt"] >= {"zero_width", "bidi_control"}


def test_scan_hidden_payloads_is_clean_on_ordinary_text(tmp_path):
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    (tree / "README.md").write_text("Just an ordinary README with no surprises.\n", encoding="utf-8")

    assert scan_hidden_payloads(tree) == []


def test_scan_hidden_payloads_skips_binary_files_without_raising(tmp_path):
    tree = tmp_path / "cloned-repo"
    tree.mkdir()
    (tree / "image.bin").write_bytes(bytes(range(256)))

    # Must not raise on undecodable content -- a crash here would mean the scan
    # silently covered nothing for the rest of the tree too.
    assert scan_hidden_payloads(tree) == []


def test_strip_hidden_payloads_removes_every_kind():
    tag_characters, zero_width, bidi_control, html_comment, base64_blob = _payload_fixtures()
    excerpt = f"See: {tag_characters}{html_comment}{zero_width}{bidi_control}{base64_blob}"

    stripped = strip_hidden_payloads(excerpt)

    assert tag_characters not in stripped
    assert zero_width not in stripped
    assert bidi_control not in stripped
    assert html_comment not in stripped
    assert base64_blob not in stripped
