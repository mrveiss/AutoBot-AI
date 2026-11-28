# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One owner-checked release and renew script (#19631): their home is ``autobot_shared/redis_utils.py``.

WHAT THIS MATCHES. A SHAPE, not a name: a Lua body that compares ``KEYS[1]``'s value to ``ARGV[1]`` and, on a
match, deletes or expires that key (``del`` / ``expire`` / ``pexpire``, with or without a ``return``) is a private
copy of ``COMPARE_AND_DELETE_LUA`` / ``COMPARE_AND_PEXPIRE_LUA`` whatever it is called. Callers go through
``delete_if_value`` / ``expire_if_value``. The home holds exactly ``SHAPES_IN_HOME`` of them.

WHAT IT DOES NOT MATCH, and why each is a recorded exception rather than a private copy:

* ``COMPARE_HOLDER_AND_DELETE_LUA`` (the home): reads the value into a ``local`` and matches a holder prefix or
  ``<holder>#<generation>``, which is not a plain equality; it is the home of that other rule (``delete_if_holder``).
* Compare-and-SET scripts (``idempotency._COMPLETE_SCRIPT``, ``rolling_summary._STORE_IF_LOCKED``): the same compare
  followed by a write, a different operation.
* ``interpretation_turn`` ``REGISTER_TURN_LUA`` / ``TAKE_LUA`` and ``entity_upsert.CLAIM_AND_WRITE_LUA``: read into a
  ``local`` and transition a state, no plain release.
* ``desktop_control_lock._RELEASE_LUA_SCRIPT``: decodes a JSON record and compares its ``owner`` field.
* ``work_claims_lua`` release / renew: ownership is structural (the key embeds the holder) and the payload is JSON.
* ``pending_claim.drop_pending_slot``: deliberately unconditional on session close (an owner decision recorded on #19631).
* ``session_state.PERSIST_IF_VERSION_LUA``: a version compare-and-set on a JSON record.
* Counters and floors (``session_lease._GENERATION_LUA``, ``password_epoch``): a ``GET`` feeding an ``INCR``.
* ``code_intelligence/redis_optimizer.py``: a generated example string, not a script the process runs.
* ``session_state.RELEASE_CLAIM_AND_MARK_LUA``: DOES match, once (its ``KEYS[1]`` compare-and-delete; the second,
  over ``KEYS[2]``, is outside the pattern). It is the one recorded exception below: a multi-key release the
  single-key helper cannot express.

A copy written through a ``local`` (``local v = redis.call('GET', ...)`` then ``if v == ARGV[1]``) is NOT matched;
the tree has none outside the home today, and a regex wide enough to find one would also match every script above.

THE ACCEPTANCE CRITERION AS WRITTEN. AC3 asks that ``git grep "redis.call('get', KEYS[1]) == ARGV[1]"`` find only the
helper file. That cannot hold: compare-and-set scripts (``idempotency._COMPLETE_SCRIPT``,
``rolling_summary._STORE_IF_LOCKED``) and the multi-key release above contain the same text. The owner confirmed on
2026-11-13 (recorded on #19631) that this shape guard, with the exceptions recorded here, replaces AC3's literal grep.

Every file asserted by name is a count, compared in both directions: a new copy fails, and an exception that stops
matching fails as stale.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

HOME = "autobot_shared/redis_utils.py"
ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
COPY = re.compile(
    r"redis\.call\(\s*['\"]get['\"],\s*KEYS\[1\]\s*\)\s*==\s*ARGV\[1\]\s*then\s*(?:return\s+)?"
    r"redis\.call\(\s*['\"](del|expire|pexpire)['\"]",
    re.IGNORECASE,
)
#: COMPARE_AND_DELETE_LUA and COMPARE_AND_PEXPIRE_LUA. COMPARE_HOLDER_AND_DELETE_LUA starts with ``local v =``.
SHAPES_IN_HOME = 2
#: Recorded exceptions: file -> how many shapes it holds, and why it is not a private copy of the helper.
EXCEPTIONS = {
    # RELEASE_CLAIM_AND_MARK_LUA: drops a claim key and a marker key in ONE script, each only while it holds the
    # token. A multi-key release; delete_if_value is single-key, so two calls would give up the atomicity.
    "autobot-backend/services/agent_terminal/session_state.py": 1,
}


def _python_files(root: Path) -> list[str]:
    """Tracked python files under ``ROOTS``; empty on an empty tree."""
    try:
        return [path for path in tracked_paths(root, *ROOTS) if path.endswith(".py")]
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return len(tracked_paths(root, "*.py"))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "one-compare-and-delete-script",
    discover=_python_files,
    reference=_all_python,
    min_fraction=0.7,
    what="tracked python files",
    roots=ROOTS,
)


def _count_shapes(root: Path, paths: list[str]) -> dict[str, int]:
    """``{path: shapes}`` for the files under *root* that hold at least one."""
    found: dict[str, int] = {}
    for rel in paths:
        path = root / rel
        if path.is_file():
            hits = len(COPY.findall(path.read_text(encoding="utf-8", errors="replace")))
            if hits:
                found[rel] = hits
    return found


def _violations(found: dict[str, int]) -> list[str]:
    """What is wrong with a ``{path: shapes}`` map: the home's count, stale or grown exceptions, private copies."""
    rest = dict(found)
    problems = []
    if (at_home := rest.pop(HOME, 0)) != SHAPES_IN_HOME:
        problems.append(f"{HOME} holds {at_home} shapes, expected {SHAPES_IN_HOME}: the pattern or the home changed")
    for rel, expected in EXCEPTIONS.items():
        if (held := rest.pop(rel, 0)) != expected:
            problems.append(f"recorded exception {rel} holds {held} shapes, expected {expected}")
    problems += [
        f"{rel} holds {n} private copy(ies): use delete_if_value / expire_if_value from {HOME}"
        for rel, n in rest.items()
    ]
    return problems


def _copies() -> dict[str, int]:
    root = repo_root()
    paths = _python_files(root)
    REACH.completed(len(paths), root)
    return _count_shapes(root, paths)


def test_only_the_home_and_the_recorded_exceptions_hold_the_shape():
    assert not _violations(_copies())


def test_the_pattern_matches_a_copy_in_either_case_and_spacing():
    assert COPY.search("if redis.call('get', KEYS[1]) == ARGV[1] then\n    return redis.call('del', KEYS[1])")
    assert COPY.search('if redis.call("GET",KEYS[1])==ARGV[1] then return redis.call("PEXPIRE", KEYS[1], ARGV[2])')
    assert COPY.search("if redis.call('GET', KEYS[1]) == ARGV[1] then redis.call('EXPIRE', KEYS[1], ARGV[2]) end")


def test_the_pattern_matches_a_copy_without_a_return():
    assert COPY.search("if redis.call('GET', KEYS[1]) == ARGV[1] then\n  redis.call('DEL', KEYS[1])\n  released = 1")


def test_the_pattern_leaves_other_operations_alone():
    assert not COPY.search("if redis.call('GET', KEYS[1]) == ARGV[1] then\n  redis.call('SET', KEYS[1], ARGV[2])")
    through_a_local = "local v = redis.call('GET', KEYS[1])\nif v == ARGV[1] then return redis.call('DEL', KEYS[1])"
    counter = "local current = tonumber(redis.call('GET', KEYS[1]) or '0')\nreturn redis.call('INCR', KEYS[1])"
    assert not COPY.search(through_a_local)
    assert not COPY.search(counter)


def test_a_planted_private_copy_is_reported(tmp_path):
    """The walker can fail: a private copy in a file that is not the home or an exception is found and named."""
    copy = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end"
    (tmp_path / "planted.py").write_text(f'RELEASE = """\n{copy}\n"""\n', encoding="utf-8")
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    found = _count_shapes(tmp_path, ["planted.py", "clean.py", "missing.py"])
    assert found == {"planted.py": 1}
    healthy = {HOME: SHAPES_IN_HOME, **EXCEPTIONS}
    assert not _violations(healthy), "the control tree itself must be clean"
    assert any("planted.py" in problem for problem in _violations({**healthy, **found}))


def test_a_lost_home_or_a_stale_exception_is_reported():
    healthy = {HOME: SHAPES_IN_HOME, **EXCEPTIONS}
    assert _violations({k: v for k, v in healthy.items() if k != HOME})
    assert _violations({k: v for k, v in healthy.items() if k not in EXCEPTIONS})
    assert _violations({**healthy, HOME: SHAPES_IN_HOME + 1})
