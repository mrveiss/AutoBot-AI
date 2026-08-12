# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GitHistoryCrawler`` returns real history (#13832).

It never did. `import git` appeared here and nowhere else in the project, and
GitPython was in no requirements file, so `self.repo` was always None and every
method returned `[]` in every environment since the class was written. The
`except ImportError` logged *"Using fallback git commands"* — there were none,
which is how a wholly inert subsystem read as a handled degradation.

So the load-bearing assertions here are **non-empty**. A test suite that only
checked shapes would have passed against the inert version for years.
"""

import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from code_intelligence.code_evolution_miner import GitCommandError, GitHistoryCrawler, _parse_numstat


def _git(repo: Path, *args: str) -> None:
    """Run git, surfacing its stderr when it fails.

    #13882: ``check=True`` with ``capture_output=True`` raises
    ``CalledProcessError``, whose message carries only the exit status — the
    captured stderr is on the exception but never printed. A CI failure here
    therefore read as a bare "exit status 128" with no indication of the cause,
    which is what made the intermittent failure undiagnosable from the log.
    """
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {repo} with exit {result.returncode}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )


def _git_init(path: Path) -> None:
    """git init with the same stderr-surfacing contract as _git (#13882)."""
    result = subprocess.run(["git", "init", "-q", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"git init failed in {path} with exit {result.returncode}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )


def _commit(repo: Path, files: dict, message: str) -> None:
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path):
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "Test Author")
    _commit(tmp_path, {"a.py": "one\n"}, "feat: add a")
    _commit(tmp_path, {"a.py": "one\ntwo\n", "b.py": "x\n"}, "refactor: extract method from a")
    _commit(tmp_path, {"c.py": "y\n"}, "fix: unrelated\n\nWith a body line.")
    return tmp_path


# ------------------------------------------------------- it returns something


def test_commits_are_returned_at_all(repo):
    """The whole defect in one assertion: this was `[]` in every environment."""
    commits = GitHistoryCrawler(str(repo)).get_commits_in_range()

    assert len(commits) == 3


def test_file_history_is_returned_at_all(repo):
    history = GitHistoryCrawler(str(repo)).get_file_history("a.py")

    assert len(history) == 2, "a.py was touched by two commits"


def test_refactoring_commits_are_detected_at_all(repo):
    found = GitHistoryCrawler(str(repo)).detect_refactoring_commits()

    assert [c["refactoring_type"] for c in found] == ["extract_method"]


def test_the_crawler_needs_no_gitpython():
    """The dependency that was never installed is gone, not made optional."""
    import code_intelligence.code_evolution_miner as miner

    assert "import git" not in Path(miner.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------- the fields callers use


def test_every_field_downstream_code_reads_is_populated(repo):
    commit = GitHistoryCrawler(str(repo)).get_commits_in_range()[0]

    assert len(commit["hash"]) == 40
    assert commit["author"] == "Test Author"
    assert commit["message"]
    assert set(commit["stats"]) == {"files", "insertions", "deletions", "lines"}


def test_timestamps_are_timezone_aware_utc(repo):
    """#13162: a naive datetime here crashed `calculate_trend`, which compares
    against `datetime.now(tz=timezone.utc)`, and made month bucketing depend on
    the server's local timezone."""
    commit = GitHistoryCrawler(str(repo)).get_commits_in_range()[0]

    assert commit["timestamp"].tzinfo is not None
    assert commit["timestamp"].utcoffset() == timedelta(0)


def test_a_multi_line_message_survives_the_parse(repo):
    """The body is last before the numstat block, so it must not swallow it."""
    commits = GitHistoryCrawler(str(repo)).get_commits_in_range()
    body_commit = next(c for c in commits if c["message"].startswith("fix: unrelated"))

    assert "With a body line." in body_commit["message"]
    assert body_commit["stats"]["files"] == 1, "the numstat block was consumed by the message"


def test_stats_count_the_lines_that_changed(repo):
    commits = GitHistoryCrawler(str(repo)).get_commits_in_range()
    refactor = next(c for c in commits if c["message"].startswith("refactor"))

    assert refactor["stats"]["files"] == 2
    assert refactor["stats"]["insertions"] == 2
    assert refactor["stats"]["lines"] == refactor["stats"]["insertions"] + refactor["stats"]["deletions"]


# ------------------------------------------------------------------ filtering


def test_the_date_range_excludes_older_commits(repo):
    future = datetime.now(timezone.utc) + timedelta(days=1)

    assert GitHistoryCrawler(str(repo)).get_commits_in_range(start_date=future) == []


def test_an_end_date_in_the_past_excludes_everything(repo):
    past = datetime.now(timezone.utc) - timedelta(days=3650)

    assert GitHistoryCrawler(str(repo)).get_commits_in_range(end_date=past) == []


def test_file_history_is_scoped_to_the_path(repo):
    history = GitHistoryCrawler(str(repo)).get_file_history("c.py")

    assert len(history) == 1
    assert history[0]["message"].startswith("fix: unrelated")


def test_a_path_that_looks_like_a_flag_is_not_read_as_one(repo):
    """`--` separates revisions from paths, so a hostile-looking path cannot
    become an option."""
    assert GitHistoryCrawler(str(repo)).get_file_history("--all") == []


# -------------------------------------------------------------- degradation


def test_a_non_repository_degrades_rather_than_raising(tmp_path):
    crawler = GitHistoryCrawler(str(tmp_path))

    assert crawler.available is False
    assert crawler.get_commits_in_range() == []
    assert crawler.get_file_history("x.py") == []
    assert crawler.detect_refactoring_commits() == []


def test_a_real_repository_reports_itself_available(repo):
    """The flag must distinguish the two cases, or "no history" is ambiguous again."""
    assert GitHistoryCrawler(str(repo)).available is True


# ------------------------- a git failure, not a missing repository (#14114)


def _corrupt_object_store(repo: Path) -> None:
    """Break git log on an otherwise-valid repository.

    ``rev-parse --git-dir`` still succeeds afterwards — the ``.git`` directory
    is real — so ``available`` stays ``True``. Only the history walk fails,
    which is exactly the shape of the CI failure in #14114: the fixture's
    temporary repository lost objects mid-test while remaining, by every
    cheaper check, a git repository.
    """
    shutil.rmtree(repo / ".git" / "objects")
    (repo / ".git" / "objects").mkdir()


def test_a_git_failure_on_an_available_repo_raises_not_degrades(repo):
    """MUST fail against the pre-#14114 code: every caller here returned ``[]``
    on any non-zero git exit, indistinguishable from "no history".

    Matches the exit code, not just the word "git" — every message here
    contains "git" (the argv, the repo path), so that alone would pass even if
    the exception carried no information about the actual failure.
    """
    crawler = GitHistoryCrawler(str(repo))
    assert crawler.available is True

    _corrupt_object_store(repo)

    with pytest.raises(GitCommandError, match="exited 128"):
        crawler.get_commits_in_range()


def test_get_file_history_raises_on_a_git_failure_too(repo):
    """Every ``_run_git`` caller gets the same treatment, not just one method."""
    crawler = GitHistoryCrawler(str(repo))
    _corrupt_object_store(repo)

    with pytest.raises(GitCommandError, match="exited 128"):
        crawler.get_file_history("a.py")


def test_get_commit_files_raises_on_a_git_failure_too(repo):
    crawler = GitHistoryCrawler(str(repo))
    commit_hash = crawler.get_commits_in_range()[0]["hash"]
    _corrupt_object_store(repo)

    with pytest.raises(GitCommandError, match="exited 128"):
        crawler.get_commit_files(commit_hash)


def test_a_genuinely_empty_window_stays_no_history_not_an_error(repo):
    """The distinction the fix exists to preserve: an intact repository with no
    commits in range is "no history", never an error (#14114).

    Pins ``available is True`` first — without it, a mutation that made the
    repo read as unavailable would produce the same ``[]`` from the
    degradation branch instead of from a successful, empty git call, and this
    test would stay green for the wrong reason.
    """
    crawler = GitHistoryCrawler(str(repo))
    assert crawler.available is True
    future = datetime.now(timezone.utc) + timedelta(days=1)

    assert crawler.get_commits_in_range(start_date=future) == []


# ------------------------- a construction-time failure is not "not a repo"


def test_a_construction_time_subprocess_failure_propagates(repo, monkeypatch):
    """A timeout or a missing git binary during the ``rev-parse`` probe must not
    be swallowed into a false ``available = False`` (#14114 finding).

    ``GitCommandError`` covers both a completed, non-zero git exit (which can
    legitimately mean "not a repository") and a subprocess-level failure that
    never got that far (which cannot). A blanket ``except GitCommandError`` in
    ``__init__`` conflated the two, so a probe timeout read exactly like "not a
    git repository" and silently degraded every subsequent call to ``[]`` —
    reproducing this issue's core defect one call earlier, at construction.
    """
    import code_intelligence.code_evolution_miner as miner_module

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(miner_module.subprocess, "run", _timeout)

    with pytest.raises(GitCommandError):
        GitHistoryCrawler(str(repo))


def test_a_non_repository_still_degrades_with_the_real_subprocess(tmp_path):
    """The one case that legitimately swallows a ``GitCommandError``: a
    completed ``rev-parse`` that exited non-zero because there is no
    repository here at all. Runs the real subprocess, not a monkeypatch, so a
    change to the exit-code plumbing cannot make both this and the timeout
    test pass for the same wrong reason."""
    crawler = GitHistoryCrawler(str(tmp_path))

    assert crawler.available is False


# ---------------------------------------------------------------- numstat parsing


def test_a_binary_file_counts_as_changed_with_no_line_changes():
    """git reports binaries as `-\\t-\\tpath`; dropping them would undercount files."""
    stats = _parse_numstat("-\t-\timage.png\n3\t1\tcode.py\n")

    assert stats == {"files": 2, "insertions": 3, "deletions": 1, "lines": 4}


def test_an_empty_numstat_is_zero_not_an_error():
    assert _parse_numstat("") == {"files": 0, "insertions": 0, "deletions": 0, "lines": 0}


def test_a_binary_only_commit_is_still_a_commit(repo):
    _commit(repo, {"blob.bin": b"\x00\x01\x02"}, "chore: add a binary")

    commits = GitHistoryCrawler(str(repo)).get_commits_in_range()
    binary = next(c for c in commits if c["message"].startswith("chore: add a binary"))

    assert binary["stats"]["files"] == 1
    assert binary["stats"]["lines"] == 0


# ------------------------------- the consumers, against non-empty input


def test_analyze_evolution_actually_analyses(repo, caplog):
    """`CodeEvolutionMiner` had never received a non-empty commit list.

    Two defects surfaced the moment it did, and both were invisible before:
    `_analyze_commit_patterns` guarded on `self.repo`, an attribute the class
    never had, and `self.repo_path / item` was a Path operation on a `str`. The
    first short-circuited on an always-None attribute so the second could never
    raise — an inert subsystem hiding a broken one.
    """
    from code_intelligence.code_evolution_miner import CodeEvolutionMiner

    with caplog.at_level("ERROR"):
        report = CodeEvolutionMiner(str(repo)).analyze_evolution()

    assert report["commits_analyzed"] == 3
    failures = [r.getMessage() for r in caplog.records if "Failed to analyze commit" in r.getMessage()]
    assert failures == [], f"commits failed to analyse: {failures[:2]}"


def test_analyze_evolution_propagates_a_git_failure_mid_walk(repo, monkeypatch):
    """A git failure while analysing one commit's files must reach the router,
    not disappear into a logged warning (#14114 finding).

    `_analyze_commit_patterns` wraps `crawler.get_commit_files` in its own
    broad `except Exception`, which previously swallowed a `GitCommandError`
    the same way it swallows a genuinely unreadable file — so
    `analyze_evolution` returned `commits_analyzed: N, emerging_patterns: []`
    with no indication anything had failed. Every `api/code_intelligence.py`
    and `api/analytics_evolution.py` endpoint that calls `analyze_evolution`
    wraps it in `except Exception`, so once this propagates out of
    `CodeEvolutionMiner`, those endpoints turn it into a real error response
    instead of a well-formed empty one — no router change required.

    Reproduces the mid-walk failure directly (a commit whose *objects* vanish
    after the initial `git log` already listed it — a concurrent `git gc`, or
    the tmp-retention race that motivated #14114) rather than via git
    corruption, so the test is deterministic and does not depend on which
    specific commit git happens to touch first.
    """
    from code_intelligence.code_evolution_miner import CodeEvolutionMiner, GitCommandError

    def _boom(self, commit_hash):
        raise GitCommandError(f"git ('show', ...) exited 128 in <repo>: fatal: bad object {commit_hash}")

    monkeypatch.setattr(GitHistoryCrawler, "get_commit_files", _boom)

    with pytest.raises(GitCommandError, match="exited 128"):
        CodeEvolutionMiner(str(repo)).analyze_evolution()


def test_the_miner_holds_a_path_not_a_string(repo):
    """`repo_path` is used with the `/` operator; a str made every commit fail."""
    from code_intelligence.code_evolution_miner import CodeEvolutionMiner

    assert isinstance(CodeEvolutionMiner(str(repo)).repo_path, Path)


def test_commit_files_lists_what_a_commit_touched(repo):
    crawler = GitHistoryCrawler(str(repo))
    second = crawler.get_commits_in_range()[1]

    assert sorted(crawler.get_commit_files(second["hash"])) == ["a.py", "b.py"]


def test_commit_files_degrades_on_a_non_repository(tmp_path):
    assert GitHistoryCrawler(str(tmp_path)).get_commit_files("deadbeef") == []
