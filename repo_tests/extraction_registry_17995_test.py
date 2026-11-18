# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One guard for every registered extraction: no second definition or inline copy (#17995).

An extraction migrates N-1 call sites and the Nth survives, then misses every later fix
(#17982: the survivor kept substituting AutoBot's own tree after the canonical copy learned
to raise). The registry in ``extraction_registry.py`` names each concept and its canonical
site; this test fails when any other non-test module in the swept roots matches the
concept's detector.

Contrast pair per detector: a copy the detector must flag and a lookalike it must not,
so "no offenders" cannot mean "the detector matches nothing".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from autobot_shared.testfile_names import is_test_filename
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.extraction_registry import (
    DEFAULT_ROOTS,
    GUARDED,
    GUARDED_ELSEWHERE,
    REGISTRY,
    TOOLING_ROOTS,
    defines_top_level,
    inlines_egress_decision,
    inlines_source_root,
    inlines_wav_duration,
    seeds_post_commit_list,
)

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = DEFAULT_ROOTS + TOOLING_ROOTS


def _is_source_python(rel: str) -> bool:
    """A non-test Python file: the only kind that can be a second definition of a concept."""
    return rel.endswith(".py") and not (
        is_test_filename(rel, include_js=False, include_conftest=False) or "/tests/" in rel
    )


def _source_population(root: Path) -> list[str]:
    """Every tracked .py under the swept roots; entries filter test modules out themselves."""
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if rel.endswith(".py")]
    except EmptyEnumeration:
        return []


REACH = declare(
    "extraction-registry-sweep",
    discover=_source_population,
    what="python source and tests",
    roots=_ROOTS,
    growth=300,
)


def _offenders() -> list[str]:
    root = repo_root()
    found: list[str] = []
    for rel in REACH.examined(root):
        try:
            tree = parse_cache.parse((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for entry in (e for e in REGISTRY if e.status == GUARDED):
            allowed = {entry.canonical, *(p for p, _ in entry.allowed)}
            if not rel.startswith(tuple(r + "/" for r in entry.roots)):
                continue
            if not entry.include_tests and not _is_source_python(rel):
                continue
            if rel not in allowed and entry.detector(tree):
                found.append(f"{rel}: carries its own copy of '{entry.concept}' (canonical: {entry.canonical})")
    return found


def test_every_entrys_roots_are_swept_and_non_trivially() -> None:
    """A concept whose roots matched few files is "did not look", not "clean"."""
    swept = REACH.examined(repo_root())
    for e in (e for e in REGISTRY if e.status == GUARDED):
        n = sum(1 for rel in swept if rel.startswith(tuple(r + "/" for r in e.roots)))
        assert n > 100, f"'{e.concept}': only {n} files fall under {e.roots}"


def test_no_module_outside_the_canonical_site_carries_a_registered_concept() -> None:
    offenders = _offenders()
    assert not offenders, (
        f"{len(offenders)} private copy/copies of an extracted concept:\n  "
        + "\n  ".join(offenders)
        + "\n\nCall the canonical symbol instead (#17995)."
    )


def test_every_entry_is_well_formed_and_its_canonical_symbol_exists() -> None:
    root = repo_root()
    for e in REGISTRY:
        assert e.status in {GUARDED, GUARDED_ELSEWHERE, "deferred", "waiting"}, e.concept
        if e.status == GUARDED:
            assert e.detector is not None, f"{e.concept}: GUARDED needs a detector"
            leaf = e.symbol.rsplit(".", 1)[-1]
            names = {
                n.name
                for n in ast.walk(parse_cache.parse((root / e.canonical).read_text(encoding="utf-8")))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
            assert leaf in names, f"{e.canonical} does not define {leaf}; the registry names a symbol that is gone"
        elif e.status == GUARDED_ELSEWHERE:
            assert (root / e.guard).is_file(), f"{e.concept}: named guard {e.guard} does not exist"
        else:
            assert e.reason, f"{e.concept}: a {e.status} entry must say why"
        for path, why in e.allowed:
            assert why and (root / path).is_file(), f"{e.concept}: allowance {path} needs a reason and must exist"


def test_the_registry_lists_the_six_instances_of_the_issue() -> None:
    cited = {i for e in REGISTRY for i in e.issues}
    assert {"#17982", "#17994", "#13615", "#13841", "#14901", "#17941"} <= cited


_SOURCE_ROOT_COPY = (
    "async def r(sid):\n    s = await get_source(sid)\n    if s and s.clone_path:\n        return Path(s.clone_path)\n"
)
_SOURCE_ROOT_LOOKALIKE = "async def r(sid):\n    s = await get_source(sid)\n    return s.clone_path\n"


@pytest.mark.parametrize(
    ("detector", "source", "expected"),
    [
        (inlines_source_root, _SOURCE_ROOT_COPY, True),
        (inlines_source_root, _SOURCE_ROOT_LOOKALIKE, False),
        (inlines_source_root, "def r(p):\n    return Path(p.clone_path)\n", False),
        (inlines_wav_duration, "def d(w):\n    return w.getnframes() / float(w.getframerate())\n", True),
        (inlines_wav_duration, "def d(w):\n    return w.readframes(w.getnframes())\n", False),
        (inlines_egress_decision, "async def s():\n    v = await egress_governor.evaluate(platform='x')\n", True),
        (inlines_egress_decision, "def s():\n    return {'error': 'egress_denied'}\n", True),
        (inlines_egress_decision, "async def s():\n    v = await egress_governor.gate(platform='x')\n", False),
        (seeds_post_commit_list, 'session.info["_post_commit_cbs"] = []\n', True),
        (seeds_post_commit_list, "session.info[POST_COMMIT_CALLBACKS] = []\n", True),
        (seeds_post_commit_list, 'cbs = session.info.get("_post_commit_cbs")\ncbs.append(f)\n', False),
        (seeds_post_commit_list, '# session.info["_post_commit_cbs"] = []\nx = 1\n', False),
        (defines_top_level("configure_logging"), "def configure_logging():\n    pass\n", True),
        (defines_top_level("configure_logging"), "def _configure_logging():\n    pass\n", True),
        (defines_top_level("configure_logging"), "def summarise():\n    pass\n", False),
        (defines_top_level("repo_root"), "def outer():\n    def repo_root():\n        pass\n", False),
        (defines_top_level("tracked_paths"), "def _tracked_paths(r):\n    return tracked_paths(r)\n", False),
        (defines_top_level("tracked_paths"), "def _tracked_paths(r):\n    x = 1\n    return tracked_paths(r)\n", True),
    ],
)
def test_detector_contrast_pair(detector, source: str, expected: bool) -> None:
    assert detector(parse_cache.parse(source)) is expected


#: Every provider that opens a session, per service. Checking the file for ANY call would let
#: one provider keep a hand-rolled body while another satisfies the check (#15068).
_PROVIDERS = {
    "autobot-backend/user_management/database.py": ("get_async_session", "db_session_context"),
    "autobot-slm-backend/user_management/database.py": ("get_slm_session", "get_autobot_session"),
}


def _providers_not_using_the_scope(source: str, names: tuple[str, ...]) -> list[str]:
    """Names of `names` that are missing or do not call `async_session_scope`."""
    funcs = {n.name: n for n in ast.walk(parse_cache.parse(source)) if isinstance(n, ast.AsyncFunctionDef)}
    bad = []
    for name in names:
        fn = funcs.get(name)
        calls = fn is not None and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "async_session_scope"
            for n in ast.walk(fn)
        )
        if not calls:
            bad.append(name)
    return bad


def test_the_provider_check_names_the_one_that_does_not_use_the_scope() -> None:
    good = "async def a():\n    async with async_session_scope(m()) as s:\n        yield s\n"
    bad = "async def b():\n    async with m() as s:\n        yield s\n"
    assert _providers_not_using_the_scope(good + good.replace("def a", "def c"), ("a", "c")) == []
    assert _providers_not_using_the_scope(good + bad, ("a", "b")) == ["b"]
    assert _providers_not_using_the_scope(good, ("a", "gone")) == ["gone"]


@pytest.mark.parametrize("rel", sorted(_PROVIDERS))
def test_each_service_uses_the_shared_scope(rel: str) -> None:
    bad = _providers_not_using_the_scope((repo_root() / rel).read_text(encoding="utf-8"), _PROVIDERS[rel])
    assert not bad, f"#15068: {rel}: {bad} no longer open their sessions through async_session_scope"


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/user_management/database.py", True),
        ("autobot-backend/user_management/database_test.py", False),
        ("autobot-backend/tests/test_database.py", False),
        ("autobot-slm-backend/tests/conftest.py", False),
        ("autobot-backend/user_management/test_database.py", False),
        ("autobot-backend/user_management/schema.sql", False),
    ],
)
def test_the_test_path_filter_skips_tests_and_keeps_source(rel: str, expected: bool) -> None:
    assert _is_source_python(rel) is expected


def _post_commit_entry():
    return next(e for e in REGISTRY if seeds_post_commit_list is e.detector)


def _post_commit_seeders() -> tuple[list[str], int]:
    """Non-test files in the entry's roots that seed the post-commit list, and files parsed for the key."""
    entry, root = _post_commit_entry(), repo_root()
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(root):
        if not rel.startswith(tuple(r + "/" for r in entry.roots)) or not _is_source_python(rel):
            continue
        source = (root / rel).read_text(encoding="utf-8")
        if "_post_commit_cbs" not in source and "POST_COMMIT_CALLBACKS" not in source:
            continue
        parsed += 1
        if entry.detector(parse_cache.parse(source)):
            found.append(rel)
    return found, parsed


def test_the_post_commit_scan_is_not_vacuous() -> None:
    """The canonical seeder and UserService's reader both mention the key; fewer is a blind scan (#15068)."""
    _, parsed = _post_commit_seeders()
    assert parsed >= 2, f"parsed {parsed} files mentioning the post-commit key"


def test_exactly_the_canonical_site_seeds_the_post_commit_list() -> None:
    """The registry sweep proves no OTHER file seeds it; this proves the canonical one still does (#15068)."""
    seeders, _ = _post_commit_seeders()
    entry = _post_commit_entry()
    assert seeders == [entry.canonical], (
        f"#15068: {seeders} seed session.info['_post_commit_cbs']; the transaction scope lives once in "
        f"{entry.canonical}. Call `async_session_scope(<your session maker>)` instead of copying its body."
    )
