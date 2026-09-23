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
# #15473: the rule text moved out of the script into lib/commit-subject.ere, so
# "whatever the script reads from scripts/lib/" is no longer "whatever it
# sources". A fixture that ships only *.sh gives the script an unreadable rule
# file, and the script then dies at load -- which these tests would read as a
# missing message rather than as a fixture that is not a checkout.
_SOURCED_LIB = re.compile(r"lib/([A-Za-z0-9_.-]+\.(?:sh|ere))")


def _required_libs() -> list[str]:
    names = sorted(set(_SOURCED_LIB.findall(SCRIPT.read_text(encoding="utf-8"))))
    assert names, "lint-conventions.sh reads nothing from scripts/lib/ -- the pattern has drifted"
    missing = [n for n in names if not (LIB_DIR / n).is_file()]
    assert not missing, f"lint-conventions.sh reads files that do not exist: {missing}"
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
        # #14076: slashed scopes. The repo writes them for nested areas and 14
        # of the last 400 commits on main carry one, so the linter that
        # rejected them was wrong and the commits were right. Both forms are
        # pinned -- widening a character class is easy to undo by accident, and
        # nothing covered either direction before.
        ("fix(llc/frontend): wire the thing (#1234)", 0),
        ("test(hooks/guard): cover the branch (#1234)", 0),
        ("fix(llc): unslashed still passes (#1234)", 0),
        # The scope class widened by exactly one character. A scope is still a
        # scope: whitespace and a leading slash stay rejected, so this is not a
        # licence for anything bracket-shaped.
        ("fix(llc frontend): space is not a scope (#1234)", 1),
        ("fix(/llc): leading slash is not a scope (#1234)", 1),
        # #14076, same defect one step out: found by running the rule over real
        # history instead of its own fixtures. All three forms appear on
        # main and all three were rejected.
        ("a11y(frontend): honour prefers-reduced-motion (#1234)", 0),
        ("test-guard(repo_tests): count tests that run nothing (#1234)", 0),
        ("docs(architecture,design): move the docs (#1234)", 0),
        # Still a type, still a scope: a capitalised subject with no type at all
        # remains a failure, which is the one real violation in the last 400.
        ("Consolidate the thing (#1234)", 1),
        ("-bad(x): type may not start with a dash (#1234)", 1),
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


# ── SHA exemptions (#15473) ─────────────────────────────────────────────────
# Check 3 can exempt a commit by SHA, for subjects already on main that no
# longer have an author who could amend them. Several ways that goes wrong, all
# silent, so each is pinned here rather than left to review.
REPO_ROOT = SCRIPT.resolve().parent.parent
_SHA_EXEMPTION = re.compile(r"^\s*([0-9a-f]{4,40})\)\s*continue\s*;;\s*$", re.MULTILINE)
_FULL_SHA_LEN = 40


def _sha_exemptions() -> list[str]:
    return _SHA_EXEMPTION.findall(SCRIPT.read_text(encoding="utf-8"))


def _is_shallow(repo: Path) -> bool:
    res = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        env=scrubbed_git_env(),
    )
    return res.stdout.strip() == "true"


def test_the_exemption_parser_finds_what_is_actually_there() -> None:
    """A regex that matches nothing passes every test that iterates over it.

    The tests below are `for sha in _sha_exemptions()` loops, so a drifted
    pattern turns them green rather than red. Counted against an independent,
    deliberately loose scan: if the two disagree the parser has drifted, and if
    the last exemption is ever genuinely removed these tests go with it.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    loose = len(re.findall(r"^\s*[0-9a-f]{4,}[*)][^\n]*continue", src, re.MULTILINE))
    assert loose > 0, "no sha exemption found at all -- remove these tests along with the last one"
    assert (
        len(_sha_exemptions()) == loose
    ), f"the exemption parser found {len(_sha_exemptions())} of {loose} -- it has drifted"


def test_every_sha_exemption_is_a_full_sha() -> None:
    """Abbreviations were the first attempt, and they were wrong twice over.

    `%h` abbreviates to whatever is unambiguous in the LOCAL object store, so a
    ten-character pattern read off a full clone matched where it was authored
    and missed in CI's shallow checkout, which prints seven. Shortening it to
    seven fixed that and introduced the other half: `continue` skips BOTH the
    format check and the issue-reference check, so a prefix that ever collided
    would exempt an unrelated commit from the whole of check 3. A full sha has
    neither failure mode, and this test needs no git at all -- which matters,
    because the one below cannot always run.
    """
    wrong = [s for s in _sha_exemptions() if len(s) != _FULL_SHA_LEN]
    assert not wrong, f"SHA exemptions must be full {_FULL_SHA_LEN}-character shas, got: {wrong}"


def test_every_sha_exemption_names_a_commit_that_exists() -> None:
    """An exemption resolving to nothing is dead text that outlives its reason.

    SKIPPED, never passed, on a shallow checkout. `ci.yml`'s python-shard and
    `coverage.yml` both use a bare `actions/checkout@v7`, i.e. fetch-depth 1, so
    the object store there simply cannot answer. Asserting through that would
    fail red in CI for a reason that has nothing to do with the change under
    test, which is the defect this whole branch is about. "Could not look" is
    the honest report; pre-push, which has full history, is where this is
    actually checked.
    """
    if _is_shallow(REPO_ROOT):
        pytest.skip("shallow checkout: the object store cannot answer whether these commits exist")
    for sha in _sha_exemptions():
        res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            env=scrubbed_git_env(),
        )
        assert res.returncode == 0, f"SHA exemption {sha} names no commit in this repository"


def _tiny_repo(at: Path) -> Path:
    at.mkdir()
    _git(at.parent, "init", "-q", "-b", "main", str(at))
    _git(at, "config", "user.email", "t@example.invalid")
    _git(at, "config", "user.name", "t")
    (at / "a").write_text("1", encoding="utf-8")
    _git(at, "add", "-A")
    _git(at, "commit", "-q", "-m", "chore(init): one (#1)")
    return at


def _head_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.strip()


def test_shallow_detection_is_real_not_assumed(tmp_path: Path) -> None:
    """The skip above is only honest if it actually fires on a shallow store.

    Built by writing `.git/shallow`, which is what a depth-limited fetch writes
    and what git reads to answer the question -- no clone needed, and this
    repository's guard would refuse the clone anyway.
    """
    r = _tiny_repo(tmp_path / "shallow")
    assert not _is_shallow(r), "a normal repo must not read as shallow"
    (r / ".git" / "shallow").write_text(_head_of(r) + "\n", encoding="utf-8")
    assert _is_shallow(r), "a repo with .git/shallow must read as shallow"


def test_a_missing_object_is_distinguishable_from_a_present_one(tmp_path: Path) -> None:
    """`cat-file -e` must actually fail on a sha that is not there.

    The predecessor of this test used `rev-parse --disambiguate=`, which exits 0
    with empty output for a missing object -- so it could not tell a dead
    exemption from an absent one, and asserted `0 == 1` in CI instead.
    """
    r = _tiny_repo(tmp_path / "plain")

    def exists(sha: str) -> bool:
        return (
            subprocess.run(
                ["git", "-C", str(r), "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True,
                env=scrubbed_git_env(),
            ).returncode
            == 0
        )

    assert exists(_head_of(r))
    assert not exists("0" * 40)


# ── the shared rule file: fail-closed, and one rule across two engines ──────


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda p: p.unlink(), "the rule file is gone"),
        (lambda p: p.write_text("", encoding="utf-8"), "the rule file is empty"),
        (lambda p: p.write_text("# only a comment\n", encoding="utf-8"), "it holds no pattern"),
        (lambda p: p.write_text("^a: .+\n^b: .+\n", encoding="utf-8"), "which of two patterns governs is unknowable"),
    ],
)
def test_an_unusable_rule_file_is_fatal_not_clean(repo: Path, mutate, why: str) -> None:
    """#15473 review: the python reader's equivalents were tested, the bash one's were not.

    "Both readers fail closed" was asserted on one side and true only by
    inspection on the other, which is the asymmetry that lets a guard rot.
    """
    mutate(repo / "scripts" / "lib" / "commit-subject.ere")
    res = run(repo, "--all")
    assert res.returncode != 0, f"{why}: the script reported success"
    assert "commit-subject" in (res.stderr + res.stdout), f"{why}: the failure does not name the rule file"


#: One table, both engines (#15473 review). Each side previously hard-coded its
#: own expectations, so an edit to commit-subject.ere introducing a construct the
#: two engines read differently -- `\b`, an interval quantifier, a POSIX bracket
#: class -- would be caught only if someone remembered to update both tables the
#: same way. The point of a shared rule file is that nobody has to remember.
_CROSS_ENGINE_VECTORS = [
    ("fix(deps): bump a pinned floor (#17304)", True),
    ("fix(llc/frontend): slashed scope (#123)", True),
    ("docs(architecture,design): comma-joined scope (#123)", True),
    ("tech-debt: hyphenated type, no scope (#123)", True),
    ("a11y(ui): digits in the type (#123)", True),
    ("fix(deps+security): the subject that landed on main (#17304)", False),
    ("fix(/llc): scope starting with a separator (#123)", False),
    ("fix(-llc): scope starting with a hyphen (#123)", False),
    ("Fix(deps): capitalised type (#123)", False),
    ("no type at all (#123)", False),
    ("fix(deps):no space after the colon (#123)", False),
]


def _shared_subject_pattern() -> str:
    raw = (LIB_DIR / "commit-subject.ere").read_text(encoding="utf-8")
    lines = [ln for ln in (x.strip() for x in raw.splitlines()) if ln and not ln.startswith("#")]
    assert len(lines) == 1, f"commit-subject.ere must hold exactly one pattern, found {len(lines)}"
    return lines[0]


@pytest.mark.parametrize(("subject", "expected"), _CROSS_ENGINE_VECTORS)
def test_grep_and_python_agree_on_the_shared_pattern(subject: str, expected: bool) -> None:
    pattern = _shared_subject_pattern()
    grep_ok = subprocess.run(["grep", "-qE", pattern], input=subject, text=True, capture_output=True).returncode == 0
    python_ok = re.match(pattern, subject) is not None
    assert grep_ok == python_ok, f"engines disagree on {subject!r}: grep={grep_ok} python={python_ok}"
    assert grep_ok is expected, f"{subject!r}: expected {expected}, both engines said {grep_ok}"
