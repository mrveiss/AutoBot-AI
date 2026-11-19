# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A new code path that deletes knowledge-base data must be classified (#21383, #17038).

Knowledge-base deletes go through the approval gate (``services/kb_wipe_action.py``,
``services/claude_md_reindex_action.py``, ``services/kb_collection_delete_action.py``, one skeleton in
``services/kb_approved_delete.py``). This guard fails when a tracked, non-test source file drops an index or flushes
a database, deletes a knowledge collection or its facts (``delete_collection``, ``bulk_delete_collection_facts``) or
unlinks keys on the knowledge database, and is not in ``kb_destructive_paths_allowlist_21383.ALLOWLIST``; and when an
allowlist entry no longer matches. The detectors live in ``_kb_destructive_detect.py``.

BLIND SPOTS (what a green run does not prove)
    * ``repo_tests/``, ``docs/`` and ``tools/`` are not swept (the population and ``roots=`` say so);
    * a single-key delete (``delete("fact:1")``) is not a hit: only collection verbs, ``unlink`` and a starred
      ``delete(*keys)`` are;
    * a delete through a pipeline (``pipe.delete(...)``) or through ``getattr(obj, "delete_collection")`` is not seen
      unless the file also matches another kind;
    * ``key-delete`` is a FILE-level heuristic: a file that opens the knowledge database anywhere and unlinks or
      bulk-deletes anywhere is a hit, whether or not the two touch the same client;
    * an allowlisted file is classified as a whole: a NEW caller of an allowlisted function, such as
      ``knowledge/index.py::rebuild_chromadb_index`` (no caller today), is not detected.
"""

from pathlib import Path

from repo_tests._kb_destructive_detect import (
    COLLECTION_DELETE,
    INDEX_OR_FLUSH,
    KEY_DELETE,
    kinds_in,
)
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.kb_destructive_paths_allowlist_21383 import ALLOWLIST

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SUFFIXES = (".py", ".sh")
_SKIP_PREFIXES = ("repo_tests/", "docs/", "tools/")
#: Files that only NAME the verbs as data (a permission map, a docstring list), never run them.
_NAMES_ONLY = (
    "autobot_shared/auth/mcp_tool_permissions.py",
    "autobot-backend/services/mcp_dispatch.py",
)


def _discover(root: Path) -> list[str]:
    """Every tracked .py/.sh path outside the skipped trees; an empty tree yields [] so the floor raises."""
    try:
        paths = tracked_paths(Path(root), ".")
        return [p for p in paths if p.endswith(_SUFFIXES) and not p.startswith(_SKIP_PREFIXES)]
    except EmptyEnumeration:
        return []


#: Every top-level path that holds a tracked .py/.sh file, written out so a new top-level tree is a decision here and
#: in `_reach_declared_scopes.py` (#17844), not a silent gap in the sweep.
_ROOTS = (
    ".claude",
    ".github",
    "autobot-backend",
    "autobot-browser-worker",
    "autobot-frontend",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "autobot-slm-backend",
    "autobot-slm-frontend",
    "autobot-tts-worker",
    "autobot_shared",
    "check-grafana-health.sh",
    "conftest.py",
    "data",
    "debug",
    "docker",
    "install.sh",
    "libs",
    "main.py",
    "pipeline-scripts",
    "plugins",
    "run_agent.sh",
    "scripts",
    "site",
    "sync-frontend.sh",
    "verify_causal_extractor.py",
)
#: Non-vacuity: the sweep must have read a real tree. Measured 7894 tracked .py/.sh files outside repo_tests/,
#: docs/ and tools/ (2026-11-19); the pin sits below it with growth 400 until it lands on the base (#19676).
REACH = declare(
    "kb-destructive-paths",
    discover=_discover,
    roots=_ROOTS,
    floor=7800,
    growth=400,
    what="tracked .py/.sh files outside repo_tests/, docs/ and tools/",
)


def _candidates() -> list[str]:
    paths = _discover(repo_root())
    REACH.completed(paths, repo_root())
    return [p for p in paths if "/tests/" not in p and p not in _NAMES_ONLY and not is_test_filename(p)]


def _kinds_by_file() -> dict[str, set[str]]:
    root = Path(repo_root())
    found: dict[str, set[str]] = {}
    for rel in _candidates():
        try:
            kinds = kinds_in((root / rel).read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeDecodeError):
            continue
        if kinds:
            found[rel] = kinds
    return found


def _destructive_files() -> set[str]:
    return set(_kinds_by_file())


def test_the_sweep_is_not_vacuous():
    found = _kinds_by_file()
    assert INDEX_OR_FLUSH in found["autobot-backend/services/kb_wipe_redis.py"]
    assert COLLECTION_DELETE in found["autobot-backend/services/kb_collection_delete_action.py"]
    assert KEY_DELETE in found["autobot-backend/services/claude_md_reindex_action.py"]


def test_every_destructive_file_is_classified():
    unclassified = sorted(_destructive_files() - set(ALLOWLIST))
    assert not unclassified, (
        f"{unclassified} delete knowledge data (drop an index, flush a database, delete a collection or its facts, "
        "unlink knowledge keys). Route knowledge deletes through a proposal executor "
        "(services.kb_wipe_action, services.claude_md_reindex_action, services.kb_collection_delete_action; #17038); "
        "classify a non-knowledge one in repo_tests/kb_destructive_paths_allowlist_21383.py"
    )


def test_no_stale_allowlist_entry():
    stale = sorted(set(ALLOWLIST) - _destructive_files())
    assert not stale, f"{stale} no longer delete knowledge data; remove them (the mapping only shrinks)"


def _kinds(source: str, name: str = "planted.py") -> set[str]:
    return kinds_in(source, name)


def test_planted_destructive_call_is_detected():
    assert INDEX_OR_FLUSH in _kinds('r.execute_command("FT.DROPINDEX", name, "DD")', "planted.sh")
    assert INDEX_OR_FLUSH in _kinds("redis_conn.flushdb()")


def test_planted_collection_deletes_are_detected():
    assert COLLECTION_DELETE in _kinds("async def f(kb):\n    await kb.delete_collection(collection_id='c')\n")
    assert COLLECTION_DELETE in _kinds("await kb.bulk_delete_collection_facts(collection_id=c, confirm=True)")
    assert COLLECTION_DELETE in _kinds("await asyncio.to_thread(chroma.delete_collection, name=n)")


def test_a_definition_alone_is_not_a_collection_delete():
    assert COLLECTION_DELETE not in _kinds(
        "class KB:\n    async def delete_collection(self, collection_id):\n        pass\n"
    )


def test_planted_key_deletes_on_the_knowledge_db_are_detected():
    unlink = "r = get_redis_client(database='knowledge')\nr.unlink(*keys)\n"
    bulk = "r = default_client('knowledge')\nr.delete(*keys)\n"
    const = "DATABASE = 'knowledge'\nr = make(DATABASE)\nr.unlink('doc:1')\n"
    enum = "r = get_redis_client(RedisDatabase.KNOWLEDGE)\nr.unlink(*keys)\n"
    assert all(KEY_DELETE in _kinds(src) for src in (unlink, bulk, const, enum))


def test_key_delete_detector_controls_do_not_fire():
    other_db = "r = get_redis_client(database='main')\nr.unlink(*keys)\n"
    single_key = "r = get_redis_client(database='knowledge')\nr.delete('fact:1')\n"
    file_unlink = "p = Path('x')\np.unlink(missing_ok=True)\nr = get_redis_client(database='knowledge')\n"
    os_unlink = "import os\nos.unlink(tmp)\nr = get_redis_client(database='knowledge')\n"
    assert not any(KEY_DELETE in _kinds(src) for src in (other_db, single_key, file_unlink, os_unlink))
