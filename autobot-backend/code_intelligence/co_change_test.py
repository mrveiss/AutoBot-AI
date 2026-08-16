# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Co-change coupling over real git history (#13639).

The property that decides whether this is useful or noise: **a file touched by
every commit must not read as coupled to everything.** A raw co-change count says
the changelog is the most coupled file in the repo. Normalising by the *larger* of
the two change counts is what makes the number mean something, so that is what the
tests here pin — on a real repository built in a tmpdir, because the input is git
and a fake would not exercise the part that costs.
"""

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from code_intelligence.co_change import CoChangeAnalyzer, CoChangePair
from code_intelligence.code_evolution_miner import GitCommandError, GitHistoryCrawler

#: Supplied by :func:`hermetic_git_env` to any fixture building a throwaway repo.
#: Config is nulled so the runner's global git config cannot leak in. Identity is
#: deliberately NOT here: an env-level identity silently outranks the repo-level
#: ``git config user.name`` a fixture sets, so a sibling asserting on an author
#: name would get this one instead of its own.
_SUPPLIED_GIT_VARS = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

#: This file's identity, layered on top. Supplied via the environment so the
#: fixture does not depend on the runner having a global git identity configured.
_FIXTURE_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "a@b.c",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "a@b.c",
}


def _fixture_git_env() -> dict:
    """:func:`hermetic_git_env` plus this file's own identity."""
    return {**hermetic_git_env(), **_FIXTURE_IDENTITY}


def hermetic_git_env() -> dict:
    """A git environment that cannot reach outside the repo passed to ``-C``.

    #13983: with ``GIT_INDEX_FILE`` exported, every xdist worker stages into
    **one** index while committing in its **own** tmpdir repo, so a worker
    commits a tree whose blobs live in another worker's object store:

        error: invalid object 100644 <sha> for 'solo_12.py'
        error: Error building trees

    That reads as repository corruption and is nowhere near the code under test.

    #13882: the same failure came back after that fix, with a second line of
    ``error: bad tree object HEAD``. #13983 stripped a hand-written LIST of nine
    variables, which is a denylist -- narrower than its own subject, and silently
    wrong for the tenth. Git has more than nine such variables and gains new ones
    between releases, so the list could only ever be correct for the failures
    already seen.

    Inverted here: strip **everything** beginning with ``GIT_``, then add back
    exactly what the fixture needs. The fixture runs only local commands in a
    throwaway repo, so nothing inherited is load-bearing, and a variable git adds
    next year is stripped without anyone updating a list. Identity is supplied
    too, so this does not depend on the runner having a global git identity.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_SUPPLIED_GIT_VARS)
    return env


def _git(repo: Path, *args: str) -> None:
    """Run git, surfacing its stderr when it fails.

    #13882: ``check=True`` with ``capture_output=True`` raises
    ``CalledProcessError``, whose message carries only the exit status — the
    captured stderr is on the exception but never printed. A CI failure here
    therefore read as a bare "exit status 128" with no indication of the cause,
    which is what made the intermittent failure undiagnosable from the log.
    """
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=_fixture_git_env())
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {repo} with exit {result.returncode}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )


def _git_init(path: Path) -> None:
    """git init with the same stderr-surfacing contract as _git (#13882)."""
    result = subprocess.run(["git", "init", "-q", str(path)], capture_output=True, text=True, env=_fixture_git_env())
    if result.returncode != 0:
        raise AssertionError(
            f"git init failed in {path} with exit {result.returncode}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )


def _commit(repo: Path, files: dict, message: str) -> None:
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path):
    """A repo whose history contains one genuinely coupled pair and one busy file."""
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")

    # schema.py and serializer.py always move together — the signal.
    # changelog.md moves in every commit — the noise the formula must reject.
    for i in range(6):
        _commit(
            tmp_path,
            {
                "schema.py": f"schema v{i}\n",
                "serializer.py": f"serializer v{i}\n",
                "changelog.md": f"entry {i}\n",
            },
            f"coupled change {i}",
        )
    # Twenty commits each touching a *different* file alongside the changelog. The
    # changelog therefore co-changes once with each — busy, but coupled to nothing.
    # Pairing it repeatedly with one file would be real coupling by any measure,
    # and would say nothing about whether the formula suppresses noise.
    for i in range(20):
        _commit(tmp_path, {f"solo_{i}.py": f"v{i}\n", "changelog.md": f"entry solo {i}\n"}, f"unrelated {i}")
    return tmp_path


def _pairs(repo_path: Path, **kwargs):
    """#14114: if the git walk itself fails, this now raises ``GitCommandError``
    with the underlying git stderr rather than returning an empty file-set list.
    Before that fix, every test built on this helper failed (if at all) on a
    downstream pair-count assertion that had nothing to do with the actual
    cause — see ``test_a_git_failure_on_an_available_repo_names_the_error``.
    """
    file_sets = GitHistoryCrawler(str(repo_path)).get_commit_file_sets()
    analyzer = CoChangeAnalyzer(**kwargs)
    return analyzer.analyze(file_sets), analyzer.commits_too_large_to_pair


def _pair_names(pairs):
    return {(p.source, p.target) for p in pairs}


# --------------------------------------------------------------- the signal


def test_a_genuinely_coupled_pair_is_found(repo):
    pairs, _ = _pairs(repo)

    assert ("schema.py", "serializer.py") in _pair_names(pairs)


def test_the_coupled_pair_is_the_strongest(repo):
    pairs, _ = _pairs(repo)

    assert pairs, "no pairs at all"
    assert (pairs[0].source, pairs[0].target) == ("schema.py", "serializer.py")
    assert pairs[0].strength == 1.0, "a pair that only ever moves together is total coupling"


def test_a_file_that_usually_changes_alone_is_not_coupled(tmp_path):
    """The denominator must count **every** change, not only paired ones.

    Discarding single-file commits before counting silently redefines
    ``changes(A)`` as "how often A changed alongside something else". On this
    repository 32% of commits touch one file, and excluding them inflated 44% of
    reported pairs past the threshold — the exact noise the normalised formula
    exists to reject, arriving by a different route.
    """
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    for i in range(20):
        _commit(tmp_path, {"busy.py": f"v{i}\n"}, f"solo {i}")
    for i in range(3):
        _commit(tmp_path, {"busy.py": f"pair {i}\n", "rare.py": f"v{i}\n"}, f"together {i}")

    pairs, _ = _pairs(tmp_path)

    assert pairs == [], "a file that changes alone 20 times was reported as coupled"


def test_solo_commits_reach_the_change_counter(tmp_path):
    """Directly: the count is history, not the paired subset."""
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"a.py": "1\n"}, "solo")
    _commit(tmp_path, {"a.py": "2\n", "b.py": "1\n"}, "pair")

    file_sets = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert {"a.py"} in file_sets, "the single-file commit never reached the analyzer"
    assert len(file_sets) == 2


# ------------------------------------------- the noise the formula must reject


def test_a_file_touched_by_every_commit_is_not_coupled_to_everything(repo):
    """The load-bearing property.

    ``changelog.md`` appears in all 26 commits, so a raw count makes it the most
    coupled file in the repo. Dividing by the larger change count gives
    6/26 = 0.23 against ``schema.py`` — below threshold, correctly.
    """
    pairs, _ = _pairs(repo)

    involved = [p for p in pairs if "changelog.md" in (p.source, p.target)]
    assert involved == [], f"the busy file was reported as coupled: {[(p.source, p.target) for p in involved]}"


def test_dividing_by_the_smaller_count_would_have_reported_it(repo):
    """Names the alternative and shows why it was not chosen.

    Under ``min()``, ``changelog.md``/``schema.py`` scores 6/6 = 1.0 — the busiest
    file in the repo, reported as perfectly coupled to something it merely
    outlived.
    """
    pairs, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.0)
    busy = next(p for p in pairs if {"changelog.md", "schema.py"} == {p.source, p.target})

    assert busy.co_changes / min(busy.source_changes, busy.target_changes) == 1.0
    assert busy.strength < 0.3, "the chosen denominator failed to suppress the busy file"


# ------------------------------------------------------- thresholds and caps


def test_the_minimum_count_is_inclusive_at_its_boundary(repo):
    """Asserts both sides of the boundary, so ``>=`` cannot decay to ``>``.

    Testing only the empty side leaves the off-by-one alive: the coupled pair has
    exactly 6 co-changes, so 6 must report it and 7 must not.
    """
    at_boundary, _ = _pairs(repo, min_co_changes=6)
    above, _ = _pairs(repo, min_co_changes=7)

    assert len(at_boundary) == 1
    assert above == []


def test_the_strength_threshold_alone_changes_the_result(repo):
    """Varies one knob. The previous version moved both at once, so replacing the
    strength comparison with ``>= 0.0`` left it green — it only ever proved the
    count threshold was wired."""
    strict, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.99)
    loose, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.0)

    assert len(loose) > len(strict)


def test_the_minimum_count_alone_changes_the_result(repo):
    strict, _ = _pairs(repo, strength_threshold=0.0, min_co_changes=6)
    loose, _ = _pairs(repo, strength_threshold=0.0, min_co_changes=1)

    assert len(loose) > len(strict)


def test_pairs_are_returned_strongest_first(repo):
    """The fixture yields one pair at defaults, so the sort key needs its own case."""
    pairs, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.0)

    assert len(pairs) > 1, "fixture no longer exercises ordering"
    assert [p.strength for p in pairs] == sorted((p.strength for p in pairs), reverse=True)


def test_coupled_with_honours_its_limit(repo):
    pairs, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.0)

    assert len(CoChangeAnalyzer().coupled_with("changelog.md", pairs, limit=2)) <= 2


def test_an_over_cap_commit_is_counted_but_never_paired(tmp_path):
    """A bulk rename touched its files, so it counts; pairing them would be noise.

    Truncating to the first N would invent pairs no author ever related — worse
    than declining to pair the commit and saying so.
    """
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"a.py": "1\n", "b.py": "1\n"}, "small")
    _commit(tmp_path, {f"bulk/f{i}.py": "x\n" for i in range(12)}, "mass rename")

    analyzer = CoChangeAnalyzer(min_co_changes=1, strength_threshold=0.0, max_files_per_commit=5)
    pairs = analyzer.analyze(GitHistoryCrawler(str(tmp_path)).get_commit_file_sets())

    assert analyzer.commits_too_large_to_pair == 1
    assert not any(p.source.startswith("bulk/") or p.target.startswith("bulk/") for p in pairs)


def test_vendored_paths_never_enter_the_analysis(tmp_path):
    """They co-change because a tool wrote them, not because they depend on each other."""
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    for i in range(5):
        _commit(
            tmp_path,
            {"app.py": f"v{i}\n", "node_modules/pkg/index.js": f"v{i}\n", "helper.py": f"v{i}\n"},
            f"c{i}",
        )

    file_sets = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert not any(any("node_modules" in p for p in s) for s in file_sets)


def test_a_single_file_commit_contributes_no_pair(tmp_path):
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"only.py": "1\n"}, "solo")

    file_sets = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()
    pairs = CoChangeAnalyzer(min_co_changes=1, strength_threshold=0.0).analyze(file_sets)

    assert file_sets == [{"only.py"}], "the commit must still count toward change totals"
    assert pairs == [], "one file cannot pair with anything"


# ------------------------------------------------------------ window and shape


def test_the_window_excludes_older_commits(repo):
    """A pair that co-changed long ago is history, not structure."""
    future = datetime.now(timezone.utc) + timedelta(days=1)

    file_sets = GitHistoryCrawler(str(repo)).get_commit_file_sets(since=future)

    assert file_sets == []


def test_a_missing_repo_degrades_rather_than_raising(tmp_path):
    assert GitHistoryCrawler(str(tmp_path / "nope")).get_commit_file_sets() == []


def test_the_edge_is_a_distinct_kind_never_a_call(repo):
    """Persisted beside ``calls`` edges, never merged into them.

    A co-change edge says two files moved together, not that one invokes the
    other. Folding the kinds together would make "who calls X" unanswerable.
    """
    pairs, _ = _pairs(repo)
    edge = pairs[0].as_edge()

    assert edge["kind"] == "co_change"
    assert edge["strength"] == 1.0
    assert {"source", "target", "co_changes"} <= set(edge)


def test_coupled_with_returns_only_pairs_involving_the_path(repo):
    pairs, _ = _pairs(repo)

    for pair in CoChangeAnalyzer().coupled_with("schema.py", pairs):
        assert "schema.py" in (pair.source, pair.target)


def test_the_analyzer_needs_no_git_at_all():
    """Takes file sets, not a repo — so the expensive walk stays a separate step."""
    sets = [{"a.py", "b.py"}, {"a.py", "b.py"}, {"a.py", "b.py"}]

    pairs = CoChangeAnalyzer().analyze(sets)

    assert pairs == [
        CoChangePair(source="a.py", target="b.py", co_changes=3, source_changes=3, target_changes=3, strength=1.0)
    ]


def test_non_ascii_paths_are_not_c_quoted(tmp_path):
    """Git C-quotes non-ASCII paths unless told not to.

    Left quoted, the key is an octal-escaped mangle that can never match a
    filesystem-derived path — and worse, it depends on the *reader's*
    ``core.quotepath`` setting, so the same repository yields different identities
    for different people.
    """
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"lätïn.py": "1\n", "plain.py": "1\n"}, "unicode")

    paths = set().union(*GitHistoryCrawler(str(tmp_path)).get_commit_file_sets())

    assert "lätïn.py" in paths, f"path came back quoted or mangled: {sorted(paths)}"
    assert not any(p.startswith('"') for p in paths)


def test_a_quoted_vendored_path_cannot_slip_past_the_filter(tmp_path):
    """The filter splits on path segments, so a leading quote would defeat it."""
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"node_modules/pkg/ä.js": "1\n", "app.py": "1\n"}, "vendored unicode")

    paths = set().union(*GitHistoryCrawler(str(tmp_path)).get_commit_file_sets())

    assert not any("node_modules" in p for p in paths)


def test_a_failing_git_call_is_logged_not_swallowed(tmp_path, caplog):
    """A non-repository path degrades to an empty result, but is still logged.

    This is the "not a repository" branch, distinguished from a genuine git
    failure on an *available* repository — see
    ``test_a_git_failure_on_an_available_repo_names_the_error`` below, which is
    the branch that must raise rather than degrade (#14114).
    """
    with caplog.at_level("WARNING"):
        result = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert result == []
    assert any("git" in r.getMessage() for r in caplog.records), "a git failure produced no log line"


def test_a_git_failure_on_an_available_repo_names_the_error(tmp_path):
    """A corrupted object store must not read as "no coupling found" (#14114).

    This reproduces the real CI failure behind #14114: a temporary repository's
    object store was lost mid-test, ``_run_git`` returned ``""`` on the exit-128
    failure, ``get_commit_file_sets`` read that as "no history", and
    ``co_change_test.py::test_the_minimum_count_is_inclusive_at_its_boundary``
    then failed on a bogus ``assert 0 == 1`` — an assertion about pair counts
    that had nothing to do with the actual defect.

    Unlike a non-repository path, this repo passes ``rev-parse --git-dir`` at
    construction time — ``available`` is ``True`` — and only fails later, when
    ``git log`` cannot read its own objects. That failure must reach the
    caller as a named git error, not disappear into an empty list.

    MUST fail against the pre-#14114 code: ``_run_git`` returned ``""`` on any
    non-zero exit and every caller treated that as an empty history.
    """
    _git_init(tmp_path)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"a.py": "1\n"}, "solo")

    crawler = GitHistoryCrawler(str(tmp_path))
    assert crawler.available is True, "the repo is valid before its object store is corrupted"

    shutil.rmtree(tmp_path / ".git" / "objects")
    (tmp_path / ".git" / "objects").mkdir()

    with pytest.raises(GitCommandError, match="exited 128"):
        crawler.get_commit_file_sets()


def test_a_genuinely_empty_window_is_not_an_error(repo):
    """A repo with real history but zero commits in range stays "no history",
    never an error (#14114) — the distinction the fix exists to preserve.

    Pins ``available is True`` first — without it, a mutation that made the
    repo read as unavailable would produce the same ``[]`` from the
    degradation branch instead of from a successful, empty git call.
    """
    crawler = GitHistoryCrawler(str(repo))
    assert crawler.available is True
    future = datetime.now(timezone.utc) + timedelta(days=1)

    assert crawler.get_commit_file_sets(since=future) == []


def test_the_default_window_is_actually_applied():
    """The window constant was previously declared, documented and read by nothing."""
    from code_intelligence.co_change import COCHANGE_WINDOW_DAYS, default_window_start

    delta = datetime.now(timezone.utc) - default_window_start()

    assert abs(delta.days - COCHANGE_WINDOW_DAYS) <= 1


# ------------------------------------------- the repo named is the repo read (#13983)


def test_the_crawler_reads_the_repo_it_was_given_not_the_ambient_one(repo, tmp_path, monkeypatch):
    """``GIT_DIR`` must not silently redirect the crawler to another repository.

    Git treats ``GIT_DIR`` as higher precedence than ``-C``, so an exported one
    makes the path argument advisory. The caller then gets a perfectly plausible
    history for the wrong tree — no error, no empty result, just an answer about
    something else. That is strictly worse than failing.

    Reproduced rather than asserted abstractly: a second repo with a distinct
    file is built, ``GIT_DIR`` is pointed at it, and the crawler must still
    report the fixture's files.
    """
    other = tmp_path.parent / "other_repo_13983"
    other.mkdir()
    _git_init(other)
    _git(other, "config", "user.email", "a@b.c")
    _git(other, "config", "user.name", "t")
    _commit(other, {"decoy.py": "x\n"}, "decoy commit")

    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    file_sets = GitHistoryCrawler(str(repo)).get_commit_file_sets()
    seen = {path for commit in file_sets for path in commit}

    assert "schema.py" in seen, "the crawler did not read the repository it was given"
    assert "decoy.py" not in seen, "GIT_DIR redirected the crawler to the ambient repository"


def test_the_production_git_env_strips_every_git_variable():
    """The rule, not a list of names.

    This test previously pinned a seven-name denylist, arguing that stripping
    ``GIT_*`` wholesale would break unrelated callers because ``GIT_AUTHOR_*``
    and ``GIT_SSH_COMMAND`` are legitimate. The call graph refutes it:
    ``git_env()`` has exactly one consumer, ``_run_git``, whose every call site
    is ``rev-parse --git-dir`` / ``log`` / ``show`` against a local path with
    ``-C``. Nothing commits, so ``GIT_AUTHOR_*`` is inert; nothing clones or
    fetches, so ``GIT_SSH_COMMAND`` is inert. (``skills/external_importer.py``
    does fetch, but through its own ``_run_git`` with a different signature — it
    never touches this environment.)

    The concern was real in principle and false for this module, and the cost of
    being wrong the other way is a crawler silently reporting another
    repository's history (#13983, #13882).
    """
    from code_intelligence.code_evolution_miner import git_env

    for var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        # Never on the seven-name list. The rule covers them without anyone
        # noticing they were missing.
        "GIT_COMMON_DIR",
        "GIT_CEILING_DIRECTORIES",
        "GIT_INDEX_VERSION",
        "GIT_TEST_SOMETHING_NEW",
    ):
        os.environ[var] = "/somewhere/else"
        try:
            assert var not in git_env(), f"{var} outranks -C but survives"
        finally:
            del os.environ[var]

    import os as _os

    _os.environ["GIT_DIR"] = "/nowhere"
    try:
        assert "GIT_DIR" not in git_env()
        assert "PATH" in git_env(), "the environment was emptied rather than filtered"
    finally:
        _os.environ.pop("GIT_DIR", None)


# ---------------------------------------------------------------------------
# #13882 — the hermetic environment itself, asserted directly.
#
# #13983 stripped a hand-written list of nine GIT_* variables and the corruption
# came back through a tenth. These assert the RULE ("nothing inherited beginning
# with GIT_ survives"), not the nine names that were known at the time.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leaked",
    [
        "GIT_INDEX_FILE",  # #13983's original culprit
        "GIT_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        # Never on any denylist. A future git release adding one of these is the
        # whole reason the rule replaced the list.
        "GIT_INDEX_VERSION",
        "GIT_LITERAL_PATHSPECS",
        "GIT_ATTR_NOSYSTEM",
        "GIT_TEST_SOMETHING_NEW",
    ],
)
def test_no_inherited_git_variable_survives(monkeypatch, leaked):
    monkeypatch.setenv(leaked, "/somewhere/shared")

    assert leaked not in hermetic_git_env()


def test_the_variables_the_fixture_needs_are_supplied(monkeypatch):
    """Stripping everything means identity has to be put back, or the fixture
    depends on the runner having a global git identity configured."""
    for name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_EMAIL", "GIT_CONFIG_GLOBAL"):
        monkeypatch.delenv(name, raising=False)

    env = _fixture_git_env()

    assert env["GIT_AUTHOR_NAME"] == "t"
    assert env["GIT_COMMITTER_EMAIL"] == "a@b.c"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull


def test_a_supplied_variable_overrides_an_inherited_one(monkeypatch):
    """A runner exporting GIT_AUTHOR_NAME must not change what this fixture commits."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "the-runner")

    assert _fixture_git_env()["GIT_AUTHOR_NAME"] == "t"


def test_non_git_environment_is_left_alone(monkeypatch):
    """PATH and friends must survive, or git cannot be found at all."""
    monkeypatch.setenv("SOME_UNRELATED_VAR", "kept")

    env = hermetic_git_env()

    assert env["SOME_UNRELATED_VAR"] == "kept"
    assert "PATH" in env


def test_a_worker_with_a_hostile_index_file_still_commits_its_own_tree(monkeypatch, tmp_path):
    """The reproduction, end to end.

    With GIT_INDEX_FILE pointing at a shared path, a worker used to stage into
    one index while committing in its own tmpdir — producing a tree whose blobs
    live in another worker's object store. Two repos are built here under the
    same hostile value; both must succeed and stay independent.
    """
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "shared.index"))

    for name in ("repo_a", "repo_b"):
        repo = tmp_path / name
        repo.mkdir()
        _git_init(repo)
        _commit(repo, {f"{name}.py": "v0\n"}, f"initial {name}")

    for name in ("repo_a", "repo_b"):
        result = subprocess.run(
            ["git", "-C", str(tmp_path / name), "log", "--oneline"],
            capture_output=True,
            text=True,
            env=_fixture_git_env(),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.count("\n") == 1, f"{name} sees another repo's history: {result.stdout}"
