# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for optimize_agents — dry-run must be genuinely safe (#14546).

This is the ONLY optimize_agents test (#14873): the older class-based ``AgentOptimizer``
module was merged into ``optimize_agents.py`` and its useful cases live at the end of this
file (code-block stripping, front matter, cache, statistics, git backup).

``optimize_agents.py`` rewrites hand-written ``.claude/agents/*.md`` files in
place with no preview and no ``--dry-run`` before this issue. The guard this
suite exists for: :func:`process_agent_files` with ``apply_changes=False``
must perform **zero writes** — every fixture file's mtime and content must be
byte-identical after the run. ``test_dry_run_matches_apply_preview`` mutates
that guarantee (flips the default so dry-run writes anyway) and asserts the
test goes red, so the guard itself is proven to catch the regression it names.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest
from autobot_shared.paths import scrubbed_git_env

_MODULE_PATH = pathlib.Path(__file__).with_name("optimize_agents.py")

_FIXTURE_WITH_SECTION = """---
name: test-agent
---

# Test Agent

## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT
Some legacy enforcement text that should be collapsed.

---

## Other Section
Untouched content.
"""

_FIXTURE_WITHOUT_SECTION = """---
name: other-agent
---

# Other Agent

Nothing here matches the optimization pattern.
"""


def _load_module():
    """Import optimize_agents by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location("optimize_agents", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["optimize_agents"] = module
    spec.loader.exec_module(module)
    return module


optimize_agents = _load_module()


@pytest.fixture
def agent_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch ``.claude/agents``-shaped directory — never the real tree."""
    directory = tmp_path / "agents"
    directory.mkdir()
    (directory / "needs-change.md").write_text(_FIXTURE_WITH_SECTION, encoding="utf-8")
    (directory / "unchanged.md").write_text(_FIXTURE_WITHOUT_SECTION, encoding="utf-8")
    return directory


def _hashes(directory: pathlib.Path) -> dict[str, str]:
    """Hash every file's exact bytes, keyed by name."""
    return {f.name: f.read_bytes().hex() for f in sorted(directory.glob("*.md"))}


def test_dry_run_writes_nothing(agent_dir: pathlib.Path):
    """The default (apply_changes=False) must not touch disk at all."""
    before = _hashes(agent_dir)
    agent_files = sorted(agent_dir.glob("*.md"))

    summary = optimize_agents.process_agent_files(agent_files, apply_changes=False)

    after = _hashes(agent_dir)
    assert after == before, "dry-run modified file content on disk"
    assert summary["modified"] == 1
    assert summary["processed"] == 2


def test_apply_actually_rewrites(agent_dir: pathlib.Path):
    """--apply must perform the write dry-run only previewed."""
    agent_files = sorted(agent_dir.glob("*.md"))

    summary = optimize_agents.process_agent_files(agent_files, apply_changes=True)

    rewritten = (agent_dir / "needs-change.md").read_text(encoding="utf-8")
    assert "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" not in rewritten
    assert "AUTOBOT POLICIES" in rewritten
    assert summary["modified"] == 1


def test_dry_run_preview_matches_what_apply_would_write(agent_dir: pathlib.Path):
    """Dry-run's reported optimized content equals what --apply later writes."""
    target = agent_dir / "needs-change.md"
    _, _, previewed = optimize_agents.compute_optimization(target)

    optimize_agents.process_agent_files([target], apply_changes=True)

    assert target.read_text(encoding="utf-8") == previewed


def test_dry_run_matches_apply_preview(agent_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Mutation guard: if dry-run started writing, this test must go red.

    Simulates the exact regression the guard exists for by forcing
    ``_handle_agent_file`` to write even when the caller asked for a preview.
    """
    real_handle = optimize_agents._handle_agent_file

    def _always_write(agent_file: pathlib.Path, apply_changes: bool, *rest, **kw) -> dict[str, int]:
        return real_handle(agent_file, True, *rest, **kw)

    monkeypatch.setattr(optimize_agents, "_handle_agent_file", _always_write)

    before = _hashes(agent_dir)
    agent_files = sorted(agent_dir.glob("*.md"))
    optimize_agents.process_agent_files(agent_files, apply_changes=False)
    after = _hashes(agent_dir)

    assert after != before, "mutation did not reach disk — guard is not exercising the write path"


def test_atomic_write_leaves_no_partial_file_on_failure(agent_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """A failure mid-write must not leave a truncated agent file behind."""
    target = agent_dir / "needs-change.md"
    original_bytes = target.read_bytes()

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        optimize_agents.write_atomically(target, "corrupted content")

    assert target.read_bytes() == original_bytes, "original file was not left intact"
    leftover_tmp = list(agent_dir.glob(".*.tmp"))
    assert leftover_tmp == [], f"temp file(s) leaked: {leftover_tmp}"


def test_invalid_utf8_file_counts_as_error_and_run_continues(agent_dir: pathlib.Path):
    """A badly-encoded file must not abort the run for every other file.

    UnicodeDecodeError is a ValueError subclass, not an OSError — a
    ``except OSError`` alone lets it propagate straight out of
    ``process_agent_files`` and crash the whole run (#14546 review).
    """
    bad_file = agent_dir / "bad-encoding.md"
    bad_file.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    agent_files = sorted(agent_dir.glob("*.md"))
    assert len(agent_files) == 3  # needs-change.md, unchanged.md, bad-encoding.md

    summary = optimize_agents.process_agent_files(agent_files, apply_changes=False)

    assert summary["processed"] == 3
    assert summary["errors"] == 1
    # the two well-formed files were still processed despite the bad one
    assert summary["modified"] == 1


def test_empty_directory_is_loud_not_silent():
    """An empty .md glob must be reported, not read as a clean no-op."""
    summary = optimize_agents.process_agent_files([], apply_changes=False)
    assert summary["processed"] == 0
    # main() itself is the loud-failure path for this case (glob matched zero
    # files) — covered by test_main_errors_on_empty_agent_dir below.


def test_main_errors_on_empty_agent_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """main() must exit non-zero and print an explicit error, never a quiet 0."""
    empty_agents_dir = tmp_path / ".claude" / "agents"
    empty_agents_dir.mkdir(parents=True)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py"])

    exit_code = optimize_agents.main()

    assert exit_code == 1
    assert "No agent files found" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Behaviour merged in from the removed class-based AgentOptimizer (#14873)
# --------------------------------------------------------------------------

_CODE_DOC = """---
name: test-agent
description: Test agent
---

# Test Agent

## Example Usage

```python
def example():
    return "test"
```

More text here.

```bash
echo "test"
```

End of file.
"""

_STRIP = optimize_agents.OptimizeOptions(collapse_policy=False, strip_code_blocks=True)


def test_default_options_leave_code_blocks_alone():
    """Stripping is opt-in: the default run keeps every fenced block."""
    optimized, removed = optimize_agents.optimize_content(_CODE_DOC, optimize_agents.OptimizeOptions())
    assert removed == 0
    assert optimized == _CODE_DOC


def test_strip_code_blocks_removes_every_block_and_keeps_structure():
    optimized, removed = optimize_agents.optimize_content(_CODE_DOC, _STRIP)
    assert removed == 2
    for gone in ("def example()", 'echo "test"'):
        assert gone not in optimized
    for kept in ("# Test Agent", "## Example Usage", "More text here", "End of file"):
        assert kept in optimized
    assert "[Code example removed for token optimization (python)]" in optimized
    assert "[Code example removed for token optimization (bash)]" in optimized


def test_strip_code_blocks_without_language_has_no_hint():
    processed, removed = optimize_agents.strip_code_blocks("```\nx = 1\n```")
    assert removed == 1
    assert processed == "```\n[Code example removed for token optimization]\n```"


def test_front_matter_is_never_touched():
    """A fenced block inside the YAML is data, not an example: it survives byte for byte."""
    doc = "---\nname: a\nnote: |\n  ```\n  keep\n  ```\n---\n\n```sh\nx\n```\n"
    optimized, removed = optimize_agents.optimize_content(doc, _STRIP)
    assert removed == 1
    assert optimized.startswith("---\nname: a\nnote: |\n  ```\n  keep\n  ```\n---\n")


def test_unterminated_front_matter_is_treated_as_body():
    doc = "---\nname: malformed\nno closing fence\n\n```py\nx\n```\n"
    optimized, removed = optimize_agents.optimize_content(doc, _STRIP)
    assert removed == 1
    assert optimized.startswith("---\nname: malformed")


def test_strip_verbose_replaces_the_examples_section_only_when_asked():
    doc = "# A\n\n## Examples\nlots\nof\ntext\n\n## Next\nkept\n"
    verbose = optimize_agents.OptimizeOptions(collapse_policy=False, strip_verbose=True)
    optimized, _ = optimize_agents.optimize_content(doc, verbose)
    assert "lots" not in optimized
    assert "[Examples removed for token optimization]" in optimized
    assert "## Next\nkept" in optimized
    assert optimize_agents.optimize_content(doc, optimize_agents.OptimizeOptions(collapse_policy=False))[0] == doc


def test_no_collapse_policy_leaves_the_policy_section(agent_dir: pathlib.Path):
    target = agent_dir / "needs-change.md"
    changed, _, _ = optimize_agents.compute_optimization(target, optimize_agents.OptimizeOptions(collapse_policy=False))
    assert not changed


def test_options_compose_policy_collapse_and_code_stripping(agent_dir: pathlib.Path):
    target = agent_dir / "needs-change.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n```py\nx = 1\n```\n", encoding="utf-8")
    both = optimize_agents.OptimizeOptions(strip_code_blocks=True)
    _, _, optimized = optimize_agents.compute_optimization(target, both)
    assert "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" not in optimized
    assert "x = 1" not in optimized


def test_stats_are_tracked_and_dry_run_counts_them(agent_dir: pathlib.Path):
    for i in range(3):
        body = "\n".join(f"    line_{j} = {j}" for j in range(20))
        (agent_dir / f"agent-{i}.md").write_text(f"---\nname: a{i}\n---\nText\n\n```python\n{body}\n```\n", encoding="utf-8")
    files = sorted(agent_dir.glob("agent-*.md"))
    summary = optimize_agents.process_agent_files(files, apply_changes=False, options=_STRIP)
    assert (summary["processed"], summary["modified"], summary["code_blocks_removed"]) == (3, 3, 3)
    assert summary["bytes_before"] > summary["bytes_after"] > 0


def test_cache_skips_unchanged_files_until_forced(agent_dir: pathlib.Path):
    target = agent_dir / "needs-change.md"
    cache: dict[str, str] = {}
    first = optimize_agents.process_agent_files([target], True, cache=cache)
    assert first["modified"] == 1 and first["cache_misses"] == 1
    assert cache[target.name] == optimize_agents.file_hash(target)
    second = optimize_agents.process_agent_files([target], True, cache=cache)
    assert second["skipped"] == 1 and second["cache_hits"] == 1
    forced = optimize_agents.process_agent_files([target], True, cache=cache, force=True)
    assert forced["skipped"] == 0 and forced["cache_hits"] == 0


def test_cache_is_invalidated_when_the_file_changes(agent_dir: pathlib.Path):
    target = agent_dir / "unchanged.md"
    cache = {target.name: optimize_agents.file_hash(target)}
    target.write_text("Modified content", encoding="utf-8")
    assert optimize_agents.process_agent_files([target], False, cache=cache)["skipped"] == 0


def test_file_hash_is_stable_sha256_hex(agent_dir: pathlib.Path):
    target = agent_dir / "unchanged.md"
    digest = optimize_agents.file_hash(target)
    assert digest == optimize_agents.file_hash(target)
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
    assert optimize_agents.file_hash(agent_dir / "missing.md") == ""


def test_cache_from_other_options_is_not_trusted(tmp_path: pathlib.Path):
    """A policy-only run's cache must not make a later code-stripping run skip files."""
    cache_file = tmp_path / ".optimization_cache.json"
    optimize_agents.save_cache(cache_file, {"a.md": "h"}, optimize_agents.OptimizeOptions())
    assert optimize_agents.load_cache(cache_file, optimize_agents.OptimizeOptions()) == {
        "a.md": "h",
        "__options__": optimize_agents.OptimizeOptions().signature(),
    }
    assert optimize_agents.load_cache(cache_file, _STRIP) == {}
    cache_file.write_text("not json", encoding="utf-8")
    assert optimize_agents.load_cache(cache_file, _STRIP) == {}
    assert optimize_agents.load_cache(tmp_path / "absent.json", _STRIP) == {}


def test_main_cache_is_written_only_on_apply(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "a.md").write_text(_FIXTURE_WITH_SECTION, encoding="utf-8")
    monkeypatch.setattr(optimize_agents, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--cache", "--stats"])
    assert optimize_agents.main() == 0
    assert not (agents / ".optimization_cache.json").exists()
    assert "AGENT OPTIMIZATION STATISTICS" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--cache", "--apply"])
    assert optimize_agents.main() == 0
    assert (agents / ".optimization_cache.json").exists()


def _git_repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "a.md").write_text(_CODE_DOC, encoding="utf-8")
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["config", "commit.gpgsign", "false"],
        ["config", "tag.gpgsign", "false"],
        ["add", "."],
        ["commit", "-qm", "seed"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True, capture_output=True, env=scrubbed_git_env())
    return tmp_path, agents


def test_git_backup_tags_commits_and_restores(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys):
    root, agents = _git_repo(tmp_path)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    args = ["optimize_agents.py", "--apply", "--git-backup", "--strip-code-blocks", "--no-collapse-policy"]
    monkeypatch.setattr(sys, "argv", args)
    assert optimize_agents.main() == 0
    assert "def example()" not in (agents / "a.md").read_text(encoding="utf-8")
    tags = optimize_agents._backup_tags(root)
    assert len(tags) == 1
    log = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%s"], capture_output=True, text=True, check=True, env=scrubbed_git_env())
    assert log.stdout.startswith("chore(agents): optimize Claude Code agents")

    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--list-backups"])
    assert optimize_agents.main() == 0
    assert tags[0] in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--restore"])
    assert optimize_agents.main() == 0
    assert "def example()" in (agents / "a.md").read_text(encoding="utf-8")


def test_apply_without_git_backup_makes_no_tag_or_commit(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root, _ = _git_repo(tmp_path)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--strip-code-blocks"])
    assert optimize_agents.main() == 0
    assert optimize_agents._backup_tags(root) == []
    count = subprocess.run(["git", "-C", str(root), "rev-list", "--count", "HEAD"], capture_output=True, text=True, check=True, env=scrubbed_git_env())
    assert count.stdout.strip() == "1"


def test_git_backup_dry_run_makes_no_tag(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root, _ = _git_repo(tmp_path)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--git-backup", "--strip-code-blocks"])
    assert optimize_agents.main() == 0
    assert optimize_agents._backup_tags(root) == []


def test_restore_without_any_backup_tag_fails_loudly(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root, _ = _git_repo(tmp_path)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--restore"])
    assert optimize_agents.main() == 1


def test_the_shell_wrapper_runs_the_surviving_module_with_its_old_behaviour():
    wrapper = pathlib.Path(__file__).parent / "utilities" / "agent-optimize.sh"
    text = wrapper.read_text(encoding="utf-8")
    assert 'OPTIMIZER_SCRIPT="$SCRIPT_DIR/../optimize_agents.py"' in text
    assert "--apply --git-backup --cache --strip-code-blocks --no-collapse-policy" in text
    assert (pathlib.Path(__file__).parent / "optimize_agents.py").is_file()
    assert not (pathlib.Path(__file__).parent / "utilities" / "optimize_agents.py").exists()


def _git_out(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True, env=scrubbed_git_env()).stdout


def test_git_backup_commit_is_scoped_to_the_agent_files(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root, _ = _git_repo(tmp_path)
    (root / "unrelated.txt").write_text("staged elsewhere\n", encoding="utf-8")
    _git_out(root, "add", "unrelated.txt")
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--git-backup", "--cache", "--strip-code-blocks"])
    assert optimize_agents.main() == 0
    committed = _git_out(root, "show", "--name-only", "--format=", "HEAD").split()
    assert committed == [".claude/agents/a.md"]
    assert "A  unrelated.txt" in _git_out(root, "status", "--porcelain")  # still staged, not swept in


def test_a_rejected_commit_returns_1_and_names_the_backup_tag(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog):
    root, _ = _git_repo(tmp_path)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho rejected-by-hook >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--git-backup", "--strip-code-blocks"])
    assert optimize_agents.main() == 1
    tag = optimize_agents._backup_tags(root)[0]
    assert "rejected-by-hook" in caplog.text
    assert f"--restore {tag}" in caplog.text


def test_a_failed_backup_tag_returns_1_before_writing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog):
    root, agents = _git_repo(tmp_path)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    real_git = optimize_agents._git

    def failing_tag(r, *args, check=True):
        if args[:1] == ("tag",) and "-a" in args:
            raise subprocess.CalledProcessError(128, ["git", *args], stderr="fatal: tag already exists")
        return real_git(r, *args, check=check)

    monkeypatch.setattr(optimize_agents, "_git", failing_tag)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--git-backup", "--strip-code-blocks"])
    assert optimize_agents.main() == 1
    assert "def example()" in (agents / "a.md").read_text(encoding="utf-8")
    assert "tag already exists" in caplog.text


def test_strip_code_blocks_is_idempotent_and_keeps_the_language_hint():
    once, removed_once = optimize_agents.strip_code_blocks(_CODE_DOC)
    twice, removed_twice = optimize_agents.strip_code_blocks(once)
    assert removed_once == 2
    assert (twice, removed_twice) == (once, 0)
    assert "[Code example removed for token optimization (python)]" in twice


def test_contrast_a_real_block_next_to_a_placeholder_is_still_stripped():
    doc = "```\n[Code example removed for token optimization (python)]\n```\n\n```bash\necho hi\n```\n"
    out, removed = optimize_agents.strip_code_blocks(doc)
    assert removed == 1
    assert "echo hi" not in out
    assert out.startswith("```\n[Code example removed for token optimization (python)]\n```")
    # a user block that merely mentions the placeholder text is real content
    mention, count = optimize_agents.strip_code_blocks("```\n[Code example removed for token optimization] and more\n```")
    assert count == 1
    assert "and more" not in mention


def test_a_failed_write_is_an_error_not_a_modification(agent_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    def _boom(*_args, **_kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(optimize_agents, "write_atomically", _boom)
    files = sorted(agent_dir.glob("*.md"))
    summary = optimize_agents.process_agent_files(files, apply_changes=True)
    assert (summary["modified"], summary["errors"]) == (0, 1)
    assert summary["bytes_after"] == summary["bytes_before"]
    assert summary["lines_after"] == summary["lines_before"]
    assert summary["processed"] - summary["modified"] - summary["errors"] == 1  # the untouched file only


def test_contrast_a_successful_write_is_a_modification(agent_dir: pathlib.Path):
    summary = optimize_agents.process_agent_files(sorted(agent_dir.glob("*.md")), apply_changes=True)
    assert (summary["modified"], summary["errors"]) == (1, 0)
    assert summary["bytes_after"] != summary["bytes_before"]


def test_git_backup_refuses_when_the_agent_dir_has_uncommitted_changes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    root, agents = _git_repo(tmp_path)
    dirty = _CODE_DOC + "\nuncommitted edit\n"
    (agents / "a.md").write_text(dirty, encoding="utf-8")
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--git-backup", "--strip-code-blocks"])
    assert optimize_agents.main() == 1
    assert optimize_agents._backup_tags(root) == []
    assert (agents / "a.md").read_text(encoding="utf-8") == dirty  # nothing rewritten
    assert "Uncommitted changes" in caplog.text


def test_contrast_an_untracked_run_cache_does_not_block_the_backup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root, agents = _git_repo(tmp_path)
    (agents / optimize_agents._CACHE_FILENAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(optimize_agents, "project_root", lambda: root)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py", "--apply", "--git-backup", "--strip-code-blocks"])
    assert optimize_agents.main() == 0
    assert len(optimize_agents._backup_tags(root)) == 1


_PROSE_BETWEEN = "```{tag}\nx = 1\n```\n\nKeep this prose.\n\n```bash\necho hi\n```\n"


@pytest.mark.parametrize("tag", ["python3", "c++", "c#", "objective-c", "shell-session"])
def test_a_non_letter_language_tag_does_not_swallow_the_prose_after_it(tag: str):
    out, removed = optimize_agents.strip_code_blocks(_PROSE_BETWEEN.format(tag=tag))
    assert removed == 2
    assert "Keep this prose." in out
    assert f"[Code example removed for token optimization ({tag})]" in out
    assert "[Code example removed for token optimization (bash)]" in out
    assert "x = 1" not in out and "echo hi" not in out
    assert optimize_agents.strip_code_blocks(out) == (out, 0)  # still idempotent


def test_contrast_a_letters_only_tag_behaves_as_before():
    out, removed = optimize_agents.strip_code_blocks(_PROSE_BETWEEN.format(tag="python"))
    assert removed == 2
    assert "Keep this prose." in out
