# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One rate limiter: no second implementation appears outside the canonical module (#18087, #7271).

``autobot_shared.rate_limiter.RateLimiter`` is the rate limiter. #12646 said so, then
``autobot_shared/rate_limit.py`` (``IPRateLimiter``) was added beside it under a name three
characters different, four MCP modules kept hand-rolled fixed-window counters, and a session
password limiter kept a per-worker dict -- none of which a symbol-fork detector could see,
because the forks did not share a name. Their behaviours differed in ways that matter
(fail-open vs per-worker enforcement; a rejected request extending the window), so picking the
wrong one was a behaviour change, not a style choice.

WHAT THIS DETECTS (behaviour first, one name signal as a backstop), per non-test module:

  counter-dict   a dict literal carrying both ``count`` and ``reset_time`` keys -- the
                 hand-rolled fixed-window counter the four MCP modules had.
  zset-window    a module using all of ZADD, ZCARD and ZREMRANGEBYSCORE (as calls or inside a
                 Lua string) -- the Redis sorted-set sliding window.
  limiter-class  a class whose name ends in ``Limiter``.

WHAT IT IS BLIND TO, stated because a baseline cannot record what its detector never saw: a
limiter written with none of those shapes (an in-process list of timestamps under a method
named ``allow``), and anything outside the three scanned trees. The scan is a floor on
duplication, not a proof of its absence.

THE ALLOWLIST is every module that trips a detector and is NOT the canonical limiter, each with
the reason it is a different concept. It is shrink-only and BIDIRECTIONAL: a new module fails,
and an entry that no longer trips fails just as loudly, so the list cannot tolerate whatever
takes that path next.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()

SCANNED_TREES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")

#: The one rate limiter. Its companion ``rate_limiter_window`` holds the window failure
#: policies and per-process fallback it delegates to; it trips no detector by design.
CANONICAL = "autobot_shared/rate_limiter.py"

_ZSET_COMMANDS = ("zadd", "zcard", "zremrangebyscore")
_LIMITER_CLASS = re.compile(r"Limiter$")

#: module -> why it is a different concept and stays. Verified by behaviour, not by name.
DISTINCT_CONCEPTS: dict[str, str] = {
    "autobot-backend/llm_shared/cross_worker_rate_limiter.py": (
        "Redis token bucket for LLM provider quota: state is (tokens, ts), refill is continuous and "
        "fractional, burst is a capacity separate from the sustained rate. A sliding window admits `max` "
        "at once then nothing until the oldest hit ages out; a bucket admits one per 1/rate. Per-provider "
        "RPM/burst come from AUTOBOT_LLM_RL_*. Cannot be expressed as RateLimiter.acquire_window."
    ),
    "autobot-backend/integrations/rate_limiter.py": (
        "Outbound quota for GitHub/Slack calls whose pause state is corrected by the provider's own "
        "X-RateLimit-*/Retry-After response headers (apply_response_headers) -- a feedback loop the canonical "
        "class does not have. Only that header state is distinct: its request-count windows are two "
        "LocalWindowCounter instances (the canonical LOCAL-policy engine), pinned by "
        "test_integration_limiter_keeps_no_window_of_its_own."
    ),
    "autobot-backend/utils/conversation_rate_limiter.py": (
        "Outbound Claude API budget that also tracks payload size, warning thresholds and backoff "
        "advice, with a synchronous dict-returning API. A per-process budget for one client, not a "
        "request gate. Audited in #7271 as a different shape: the retired claude_api_optimization_suite "
        "(deleted in 248d6dae1e, #10796) only imported ConversationRateLimiter and its successor claude_api_integration "
        "delegates here."
    ),
    "autobot-backend/user_management/middleware/rate_limit.py": (
        "TargetedPasswordChangeRateLimiter counts FAILED attempts only (INCR + EXPIRE) and clears the "
        "counter on success, keyed per target user and per calling actor. A lockout counter, not a "
        "request-rate window."
    ),
    "autobot-backend/mcp_server/auth_throttle_store.py": (
        "Shared failed-authentication lockout state for the MCP pre-auth throttle, with an owner-decided "
        "degrade-to-per-process policy documented in the module. A lockout, not a request-rate window."
    ),
    "autobot-backend/services/workflow_automation/concurrent_limiter.py": (
        "Caps CONCURRENT in-flight workflows (acquire/release), not requests per unit time."
    ),
    "autobot-backend/utils/task_queue.py": (
        "Job queue: uses ZADD/ZCARD/ZREMRANGEBYSCORE for pending/running/completed job sets and retention "
        "trimming. No request is admitted or refused against a limit."
    ),
}


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in path


def _scanned_modules(root: Path) -> list[str]:
    """Non-test Python modules under the scanned trees.

    An empty listing returns ``[]`` so the floor raises the typed ``ReachFloorError``;
    ``reach_declarations_test`` hands every declaration an empty repository on purpose.
    """
    try:
        listed = tracked_paths(root, *SCANNED_TREES)
    except EmptyEnumeration:
        return []
    return sorted(p for p in listed if p.endswith(".py") and not _is_test_path(p))


#: Relative floor, computed from the base: a sweep that lost its reach (wrong root, inverted
#: filter) would report "nothing found" with none of the evidence.
REACH = declare(
    "one-rate-limiter-scan",
    discover=_scanned_modules,
    growth=200,
    what="non-test Python modules",
    roots=SCANNED_TREES,
)


def _zset_words(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.lower() in _ZSET_COMMANDS:
            found.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(c for c in _ZSET_COMMANDS if c in node.value.lower())
    return found


def signals(source: str) -> set[str]:
    """Which rate-limiter shapes *source* contains (empty set: none)."""
    tree = parse_cache.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if {"count", "reset_time"} <= keys:
                found.add("counter-dict")
        elif isinstance(node, ast.ClassDef) and _LIMITER_CLASS.search(node.name):
            found.add("limiter-class")
    if _zset_words(tree) >= set(_ZSET_COMMANDS):
        found.add("zset-window")
    return found


def _tripping_modules(root: Path) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for rel in REACH.examined(root):
        try:
            found = signals((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if found:
            hits[rel] = found
    return hits


# ---------------------------------------------------------------- the detector itself

_FORK_COUNTER = """
import asyncio
MAX_PER_MINUTE = 60
request_counter = {"count": 0, "reset_time": 0}
_rate_limit_lock = asyncio.Lock()
"""

_FORK_ZSET = """
async def check(redis, key, now):
    redis.zremrangebyscore(key, 0, now - 60)
    redis.zadd(key, {str(now): now})
    return redis.zcard(key)
"""

_FORK_CLASS = """
class HomeGrownRateLimiter:
    pass
"""

#: Mentions rate limiting everywhere a regex would catch it, implements nothing: docstring,
#: comment, string, an unrelated dict with a `count` key, a ZSET used for a queue (no trim).
_MENTIONS_ONLY = '''
"""Calls out to the shared rate limiter; the rate limit counter lives in RateLimiter."""
from autobot_shared.rate_limiter import RateLimiter  # the rate limiter, not a copy

# rate limit: 60 requests per minute, count and reset_time are tracked elsewhere
MESSAGE = "rate limit exceeded: count, reset_time"
stats = {"count": 0, "name": "requests"}

def enqueue(redis, key, now):
    redis.zadd(key, {"job": now})
    return redis.zcard(key)
'''


@pytest.mark.parametrize(
    ("source", "expected"),
    [(_FORK_COUNTER, "counter-dict"), (_FORK_ZSET, "zset-window"), (_FORK_CLASS, "limiter-class")],
)
def test_each_fork_shape_is_detected(source: str, expected: str) -> None:
    assert expected in signals(source)


def test_contrast_a_module_that_only_mentions_rate_limiting_is_not_flagged() -> None:
    """The contrast to the cases above: same words, no implementation."""
    assert signals(_MENTIONS_ONLY) == set()


# ---------------------------------------------------------------- the tree


def test_the_sweep_reaches_the_codebase() -> None:
    REACH.verify_floor(REPO_ROOT)


def test_the_detector_sees_the_canonical_limiter() -> None:
    """Positive control: if this is empty the sweep examined something other than the limiter."""
    assert {"limiter-class", "zset-window"} <= _tripping_modules(REPO_ROOT).get(CANONICAL, set())


def test_no_rate_limiter_implementation_outside_the_canonical_module() -> None:
    unexpected = {
        rel: sorted(found)
        for rel, found in _tripping_modules(REPO_ROOT).items()
        if rel != CANONICAL and rel not in DISTINCT_CONCEPTS
    }
    assert not unexpected, (
        f"second rate-limiter implementation(s): {unexpected}\n"
        "Use autobot_shared.rate_limiter.RateLimiter (single window: acquire_window, or "
        "rate_limiter_window.WindowQuota; pick window_failure_policy explicitly). If the behaviour is "
        "genuinely a different concept, add it to DISTINCT_CONCEPTS with the reason."
    )


def test_the_allowlist_has_no_stale_entries() -> None:
    """The other half of a ratchet: delete an entry when its module stops tripping or goes away."""
    tripping = _tripping_modules(REPO_ROOT)
    stale = sorted(rel for rel in DISTINCT_CONCEPTS if rel not in tripping)
    assert not stale, f"DISTINCT_CONCEPTS entries that no longer trip any detector (delete them): {stale}"


def test_every_distinct_concept_records_a_reason() -> None:
    assert all(len(reason) > 40 for reason in DISTINCT_CONCEPTS.values())


@pytest.mark.parametrize(
    "rel",
    [
        "autobot-backend/api/git_mcp.py",
        "autobot-backend/api/browser_mcp.py",
        "autobot-backend/api/database_mcp.py",
        "autobot-backend/api/http_client_mcp.py",
    ],
)
def test_the_mcp_modules_take_their_quota_from_the_canonical_limiter(rel: str) -> None:
    """#18087 AC1: no local counter dict or lock is left behind, and the quota is the canonical one."""
    source = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "RateLimiter(" in source
    assert "_rate_limit_lock" not in source
    assert signals(source) == set()


def test_integration_limiter_keeps_no_window_of_its_own() -> None:
    """#18087/#7271: only header state is distinct; the dual window must stay on the canonical engine."""
    source = (REPO_ROOT / "autobot-backend/integrations/rate_limiter.py").read_text(encoding="utf-8")
    assert "LocalWindowCounter" in source
    assert "deque" not in source
    assert "history" not in source
    assert "_prune" not in source
