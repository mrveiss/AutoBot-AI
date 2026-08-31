# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Table-driven tests for scripts/lint-conventions.sh (#13876).

Every case here encodes a defect found in review. The theme is one failure
mode: a check that cannot run must never report clean. Each test that pins a
"silent pass" bug is marked with the finding id it guards.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

SCRIPT = Path(__file__).resolve().parent / "lint-conventions.sh"
LIB_DIR = Path(__file__).resolve().parent / "lib"
# #13984: the script sources canonical libraries instead of carrying its own
# copies, so the throwaway repo has to ship them too -- the fixture models a
# checkout, and a checkout has scripts/lib/ in it.
#
# Derived from the script rather than listed here (#15245). A hardcoded name
# went stale the moment the script gained a second library: the source failed,
# the script aborted before printing anything, and five assertions read the
# empty output as a missing message rather than as a dead script. The fixture
# now ships whatever the script actually sources, so the next library added
# cannot silently empty this file's output again.
_SOURCED_LIB = re.compile(r"lib/([A-Za-z0-9_.-]+\.sh)")


def _required_libs() -> list[str]:
    names = sorted(set(_SOURCED_LIB.findall(SCRIPT.read_text(encoding="utf-8"))))
    assert names, "lint-conventions.sh sources no scripts/lib/*.sh -- the pattern has drifted"
    missing = [n for n in names if not (LIB_DIR / n).is_file()]
    assert not missing, f"lint-conventions.sh sources libraries that do not exist: {missing}"
    return names


def _git(repo: Path, *args: str) -> None:
    """#15246: env scrubbed -- an inherited GIT_DIR would run this against the
    real repository instead of the throwaway one at ``repo``.
    """
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=scrubbed_git_env())


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with the script available at scripts/."""
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts" / "lint-conventions.sh").write_bytes(SCRIPT.read_bytes())
    (r / "scripts" / "lint-conventions.sh").chmod(0o755)
    (r / "scripts" / "lib").mkdir(parents=True)
    for name in _required_libs():
        (r / "scripts" / "lib" / name).write_bytes((LIB_DIR / name).read_bytes())
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
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
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


# --------------------------- bot-authored commits are exempt (#13921)


def _bot_commit(repo: Path, subject: str, name: str, email: str) -> None:
    """Commit as a bot identity, the way dependabot and the auto-fix workflows do."""
    (repo / f"f{abs(hash(subject)) % 9999}.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", subject],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        },
    )


def test_a_dependabot_commit_without_an_issue_is_exempt(repo: Path) -> None:
    """The regression: this failed every dependency PR (#13921).

    Dependabot subjects are well-formed and carry no issue number because none
    exists. The exemption was present and did not fire in CI; there was no test
    covering a bot-authored commit at all, which is how that shipped.
    """
    _bot_commit(
        repo,
        "build(deps): bump the all-dependencies group",
        "dependabot[bot]",
        "49699333+dependabot[bot]@users.noreply.github.com",
    )

    result = run(repo, "--range", "HEAD~1..HEAD")

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_bot_identified_only_by_email_is_exempt(repo: Path) -> None:
    """A .mailmap rewriting the display name must not un-exempt the commit.

    Matching on name alone is one signal; the email keeps the exemption working
    when that signal is rewritten.
    """
    _bot_commit(repo, "build(deps): bump something", "Renamed By Mailmap", "x[bot]@users.noreply.github.com")

    assert run(repo, "--range", "HEAD~1..HEAD").returncode == 0


def test_a_human_commit_without_an_issue_still_fails(repo: Path) -> None:
    """The exemption must not become a hole — this is the rule being enforced."""
    (repo / "human.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix(thing): no issue number here")

    result = run(repo, "--range", "HEAD~1..HEAD")

    assert result.returncode != 0
    assert "no issue reference" in result.stdout


def test_a_rejected_commit_names_the_author_it_parsed(repo: Path) -> None:
    """So a non-firing exemption is one log line to diagnose, not an inference.

    The previous version rejected commits without saying who it thought wrote
    them, which is why #13921 took a reproduction attempt rather than a glance.
    """
    (repo / "human2.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix(thing): still no issue")

    result = run(repo, "--range", "HEAD~1..HEAD")

    assert "author='t'" in result.stdout, result.stdout


def test_a_subject_containing_the_field_separator_cannot_shift_the_parse(repo: Path) -> None:
    """The free-text field is last, so nothing after it can be displaced.

    With the subject in the middle, every later field depended on it containing
    no separator — the fault class that best fitted #13921's CI-only failure.
    """
    _bot_commit(repo, "build(deps): bump a\x1fb group", "dependabot[bot]", "d[bot]@users.noreply.github.com")

    assert run(repo, "--range", "HEAD~1..HEAD").returncode == 0


def test_a_missing_git_scope_library_is_fatal_not_clean(repo: Path) -> None:
    """#13984: the shared resolver is a hard dependency, not a nice-to-have.

    Deleting it must stop the script, not degrade it into a run that resolves
    no base and reports a clean tree — the failure shape every rule in that
    library exists to prevent.
    """
    (repo / "scripts" / "lib" / "git-scope.sh").unlink()
    res = run(repo, "--all")
    assert res.returncode != 0
    assert "refusing to report clean" in res.stderr
