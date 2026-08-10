# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Table-driven tests for scripts/lint-conventions.sh (#13876).

Every case here encodes a defect found in review. The theme is one failure
mode: a check that cannot run must never report clean. Each test that pins a
"silent pass" bug is marked with the finding id it guards.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "lint-conventions.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with the script available at scripts/."""
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts" / "lint-conventions.sh").write_bytes(SCRIPT.read_bytes())
    (r / "scripts" / "lint-conventions.sh").chmod(0o755)
    _git(r.parent, "init", "-q", "-b", "main", str(r))
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "chore(init): base (#1)")
    return r


def run(repo: Path, *args: str, denylist: str | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(repo)}
    if denylist is not None:
        p = repo / "denylist.txt"
        p.write_text(denylist, encoding="utf-8")
        env["CONVENTIONS_DENYLIST"] = str(p)
    return subprocess.run(
        ["bash", "scripts/lint-conventions.sh", *args],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_missing_denylist_with_require_flag_fails(repo: Path) -> None:
    """A guard that cannot run must fail, not pass."""
    res = run(repo, "--all", "--require-denylist")
    assert res.returncode == 1
    assert "refusing to report a pass" in res.stdout


def test_missing_denylist_without_flag_says_skipped_not_passed(repo: Path) -> None:
    res = run(repo, "--all")
    assert "SKIPPED" in res.stdout
    assert res.returncode == 0


@pytest.mark.parametrize("content", ["", "# only a comment\n", "   \n\t\n"])
def test_empty_denylist_fails_under_require(repo: Path, content: str) -> None:
    """M3 — an empty or comment-only list is the likeliest misconfiguration."""
    res = run(repo, "--all", "--require-denylist", denylist=content)
    assert res.returncode == 1
    assert "no usable entries" in res.stdout


def test_denylist_entry_starting_with_dash_is_not_parsed_as_option(repo: Path) -> None:
    """H3 — a leading '-' made grep exit 2, which was read as 'no match'."""
    (repo / "tainted.md").write_text("uses Acmeproduct here\n", encoding="utf-8")
    _git(repo, "add", "tainted.md")
    _git(repo, "commit", "-q", "-m", "docs: add (#2)")
    res = run(repo, "--all", "--require-denylist", denylist="-Acmeproduct\nAcmeproduct\n")
    assert res.returncode == 1, res.stdout
    assert "no third-party names found" not in res.stdout


def test_crlf_denylist_still_matches(repo: Path) -> None:
    """H4 — 'Name\\r' matched nothing while looking like a live guard."""
    (repo / "tainted.md").write_text("uses Acmeproduct here\n", encoding="utf-8")
    _git(repo, "add", "tainted.md")
    _git(repo, "commit", "-q", "-m", "docs: add (#2)")
    res = run(repo, "--all", "--require-denylist", denylist="Acmeproduct\r\n")
    assert res.returncode == 1, res.stdout


def test_failure_output_never_echoes_the_matched_name(repo: Path) -> None:
    """The name must not be reproduced in CI logs."""
    (repo / "tainted.md").write_text("uses Acmeproduct here\n", encoding="utf-8")
    _git(repo, "add", "tainted.md")
    _git(repo, "commit", "-q", "-m", "docs: add (#2)")
    res = run(repo, "--all", "--require-denylist", denylist="Acmeproduct\n")
    assert res.returncode == 1
    assert "Acmeproduct" not in res.stdout + res.stderr


def test_unresolvable_range_is_fatal_not_clean(repo: Path) -> None:
    """H1/H2 — a shallow clone fatals; that must never read as 'no files'."""
    res = run(repo, "--range", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef..HEAD")
    assert res.returncode == 1
    assert "does not resolve" in res.stderr
    assert "clean" not in res.stdout


def test_research_doc_without_issue_link_fails(repo: Path) -> None:
    d = repo / "docs" / "research"
    d.mkdir(parents=True)
    (d / "topic.md").write_text("# findings\nno link here\n", encoding="utf-8")
    _git(repo, "add", "-A")
    res = run(repo, "--staged")
    assert res.returncode == 1
    assert "no issue cross-link" in res.stdout


def test_research_doc_with_issue_link_passes(repo: Path) -> None:
    d = repo / "docs" / "research"
    d.mkdir(parents=True)
    (d / "topic.md").write_text("# findings\ntracked in #13876\n", encoding="utf-8")
    _git(repo, "add", "-A")
    assert run(repo, "--staged").returncode == 0


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("feat(api): add thing (#1234)", 0),
        ("chore: claim worktree x", 0),
        ("Merge branch 'x'", 0),
        ("no type here (#1234)", 1),
        ("feat(api): missing the issue ref", 1),
    ],
)
def test_commit_msg_mode(repo: Path, subject: str, expected: int) -> None:
    """M2 — subjects belong to the commit-msg stage, reading the real file."""
    msg = repo / "msg.txt"
    msg.write_text(subject + "\n", encoding="utf-8")
    assert run(repo, "--commit-msg", str(msg)).returncode == expected
