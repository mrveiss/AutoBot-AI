# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""There is ONE claim registry, and a new one cannot land quietly (#16653).

`docs/developer/AGENT_COORDINATION.md` states it as a principle: agents claim
work through `autobot_shared/coordination/work_claims.py`, and
`services/task_claim.py` is the one documented exception (#15957). Nothing
enforced it. `repo_tests/store_authority_test.py` checks that declared write
sites exist, which is a different question -- it cannot see a *new* primitive,
only a missing declared one. So a second registry could be added as an ordinary
`SET … NX EX` and nothing in CI would notice; the principle would stay true in
the document and false in the tree.

WHAT THIS MATCHES, and why each arm exists:

1. `client.set(key, value, nx=True, ex=…/px=…)` -- the Python spelling of a
   lease: create-if-absent plus an expiry. That combination is what makes a key
   a *claim* rather than a value.
2. `client.setnx(...)` / `msetnx(...)` -- create-if-absent without the TTL in
   the same call. Usually paired with a separate `expire`, which is the same
   lease in two statements.
3. A Lua script containing `redis.call('SET', …)` together with an `NX`, `EX`
   or `PX` token -- how `work_claims` itself acquires, so the arm that makes
   this guard's own subject visible. Without it `work_claims` would be exempt
   from a scan that never found it, and the exemption below would be vacuous.

WHAT IT DELIBERATELY DOES NOT MATCH, stated because a boundary a reader cannot
see is the thing that makes a guard misleading:

- `zadd(…, nx=True)` and other create-if-absent writes to a COLLECTION. They
  do not claim a key with an owner; `llc/scheduler` uses them to avoid
  overwriting a schedule entry, which is not a lock in any sense this guard is
  about.
- `hsetnx`. Its target is a field inside a hash, and no site uses it as a
  lease. If one ever does, this paragraph is where to widen the matcher --
  changing it is cheaper than a wrong exemption.
- A Lua `redis.call('SET', …)` with no NX/EX/PX token. The only one in the tree
  is `code_intelligence/redis_optimizer.py`'s *generated example* string, which
  is documentation the tool emits, not a primitive it runs.

The exemption list is FROZEN and shrink-only. Each entry names the issue that
introduced it, so "why is this allowed" is answerable without a git blame, and
`test_the_exemption_list_has_no_stale_entries` fails when an entry stops
matching, so a removal cannot leave its record behind.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root

#: Trees scanned. Frontend and infra are out of scope: a claim primitive is a
#: Redis call from Python.
_ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend", "scripts", "pipeline-scripts")

#: `redis.call('SET', ...)` inside a Lua script body.
_LUA_SET = re.compile(r"redis\.call\(\s*['\"]SET['\"]", re.I)

#: The tokens that turn such a SET into a lease acquire.
_LUA_LEASE_TOKEN = re.compile(r"['\"](EX|PX|NX)['\"]", re.I)

#: THE registry. Not an exemption -- the subject.
_THE_REGISTRY = "autobot_shared/coordination/work_claims.py"

#: Every file allowed to hold a claim-or-lock primitive today, and why.
#:
#: SHRINK-ONLY. A new entry means a second thing in the tree can claim a key
#: with an owner and a TTL, which is exactly what #16653 exists to make someone
#: argue for in review rather than discover later. The issue number is the one
#: that introduced the site, recovered with `git log -S`, not a guess.
_ALLOWED: dict[str, str] = {
    _THE_REGISTRY: "#15947 — THE claim registry. Every agent scope claim goes through it.",
    "autobot-backend/services/task_claim.py": (
        "#6468, documented as the one exception in #15957 — task IDENTITY, which a work scope is not."
    ),
    "autobot_shared/leader_lease.py": (
        "#12842 — process leadership, not work scope: which replica runs a loop, not who owns a path."
    ),
    "autobot_shared/idempotency.py": (
        "#15813 — an idempotency claim on a REQUEST, so a retry does not create twice. No owner, no renew."
    ),
    "autobot-backend/llc/sync/outbound_sync.py": "#8521 — leader election for the LLC outbound sync loop.",
    "autobot-backend/llc/notifications/router.py": "#8579 — one uvicorn worker runs the notification router.",
    "autobot-backend/llc/services/work_item_service.py": (
        "#8213 — an LLC *work item* checkout: product domain state, not agent coordination."
    ),
    "autobot-backend/services/gateway/ingest_governor.py": (
        "#14143 — inbound message dedup keyed by platform/channel/message id."
    ),
    "autobot-backend/services/run_jwt.py": "#7677 — a refreshed JTI's denylist entry, so an old token is one-use.",
    "autobot-backend/utils/celery_reliability.py": "#11607 — Celery task dedup by task id.",
    "autobot-backend/events/channel_stream.py": (
        "#14815 — a watermark, not a lock: SETNX keeps the LOWEST broken event id for a channel."
    ),
}

#: A floor, not a census. If the matcher stops finding primitives the assertions
#: below would all pass by matching nothing -- the failure mode this file exists
#: to prevent, applied to itself.
_MIN_SITES_SEEN = 12


def _iter_sources() -> list[Path]:
    root = repo_root()
    files: list[Path] = []
    for tree in _ROOTS:
        for path in sorted((root / tree).rglob("*.py")):
            posix = path.as_posix()
            if "/tests/" in posix or path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            files.append(path)
    return files


def _sites_in_source(source: str, label: str) -> list[str]:
    """Every claim-or-lock primitive in one module, as `path:line kind`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            if name == "set" and "nx" in keywords and ({"ex", "px"} & keywords):
                found.append(f"{label}:{node.lineno} set-nx-ttl")
            elif name in ("setnx", "msetnx"):
                found.append(f"{label}:{node.lineno} {name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _LUA_SET.search(node.value) and _LUA_LEASE_TOKEN.search(node.value):
                found.append(f"{label}:{node.lineno} lua-lease")
    return found


def _scan() -> list[str]:
    root = repo_root()
    sites: list[str] = []
    for path in _iter_sources():
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            sites.extend(_sites_in_source(source, path.relative_to(root).as_posix()))
        except SyntaxError:
            continue
    return sites


def _files_with_sites() -> set[str]:
    return {site.split(":", 1)[0] for site in _scan()}


def test_the_scan_reaches_the_primitives_it_guards() -> None:
    """A matcher that matches nothing makes every assertion below vacuous."""
    sites = _scan()

    assert len(sites) >= _MIN_SITES_SEEN, (
        f"only {len(sites)} claim-or-lock primitive(s) found across {', '.join(_ROOTS)}, expected at "
        f"least {_MIN_SITES_SEEN} -- this guard has stopped reaching its subject, so a green result "
        "here means nothing was looked at, not that nothing is wrong"
    )


def test_no_new_claim_or_lock_primitive_outside_the_registry() -> None:
    """#16653: one claim registry, and a second one cannot arrive quietly."""
    unexpected = sorted(site for site in _scan() if site.split(":", 1)[0] not in _ALLOWED)

    assert not unexpected, (
        "a claim-or-lock primitive outside the one claim registry:\n  "
        + "\n  ".join(unexpected)
        + "\n\nAgents claim work through autobot_shared/coordination/work_claims.py "
        "(AGENT_COORDINATION.md). Use it -- `try_acquire`/`release`/`renew` already handle "
        "subtree overlap, renewal and a conflict that names its holder. If this really is not a "
        "work claim (a leader election, a dedup key, a one-use token), add it to _ALLOWED in this "
        "file with its issue number and say in one line why it is not a second registry."
    )


def test_the_exemption_list_has_no_stale_entries() -> None:
    """Shrink-only: a file that stops holding a primitive leaves the list."""
    stale = sorted(set(_ALLOWED) - _files_with_sites())

    assert not stale, (
        "these files no longer hold a claim-or-lock primitive -- delete their entries so the "
        "exemption list cannot drift upward (#16653):\n  " + "\n  ".join(stale)
    )


def test_every_exemption_names_its_issue() -> None:
    """ "Why is this allowed" must be answerable without a git blame."""
    unexplained = sorted(path for path, reason in _ALLOWED.items() if not re.search(r"#\d{4,5}", reason))

    assert not unexplained, "every _ALLOWED entry must name the issue that introduced it:\n  " + "\n  ".join(
        unexplained
    )


def test_the_registry_itself_is_found_by_the_scan() -> None:
    """The contrast test #16653 asks for, and the one that could go vacuous.

    `work_claims` acquires in Lua, so the Python-level arms cannot see it. If
    the Lua arm regresses, this file would still pass everything above -- while
    being blind to the very module it is protecting.
    """
    assert any(site.startswith(f"{_THE_REGISTRY}:") for site in _scan()), (
        "the claim registry's own Lua acquire is no longer matched; the Lua arm has regressed and "
        "this guard is now blind to the module it exists to protect"
    )


def test_the_documented_exception_is_found_by_the_scan() -> None:
    """The other half of the contrast: task_claim's exemption is not vacuous."""
    assert any(site.startswith("autobot-backend/services/task_claim.py:") for site in _scan())


# --- Fixtures -----------------------------------------------------------------
#
# The tree cannot prove the matcher WOULD catch a new primitive -- every site in
# it is exempt by construction. These plant one.

_PLANTED_SET_NX = 'await client.set("lock:thing", "1", nx=True, ex=30)\n'
_PLANTED_SETNX = 'await client.setnx("lock:thing", "1")\n'
_PLANTED_LUA = "_ACQUIRE = \"\"\"redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2])\"\"\"\n"
_ORDINARY_SET = 'await client.set("cache:thing", "1", ex=30)\n'
_ORDINARY_ZADD = 'await client.zadd("schedule", {"a": 1}, nx=True)\n'
_ORDINARY_LUA = '_EXAMPLE = """redis.call(\'SET\', KEYS[1], ARGV[1])"""\n'


def test_the_detector_catches_a_planted_set_nx_lease() -> None:
    assert _sites_in_source(_PLANTED_SET_NX, "planted.py") == ["planted.py:1 set-nx-ttl"]


def test_the_detector_catches_a_planted_setnx() -> None:
    assert _sites_in_source(_PLANTED_SETNX, "planted.py") == ["planted.py:1 setnx"]


def test_the_detector_catches_a_planted_lua_acquire() -> None:
    assert _sites_in_source(_PLANTED_LUA, "planted.py") == ["planted.py:1 lua-lease"]


def test_an_ordinary_set_with_a_ttl_is_not_a_claim() -> None:
    """A cache write is create-or-overwrite: no owner, nothing to lose a race for."""
    assert _sites_in_source(_ORDINARY_SET, "ordinary.py") == []


def test_a_create_if_absent_write_to_a_collection_is_not_a_claim() -> None:
    assert _sites_in_source(_ORDINARY_ZADD, "ordinary.py") == []


def test_a_lua_set_without_a_lease_token_is_not_a_claim() -> None:
    """Keeps `redis_optimizer`'s generated example out; see the module docstring."""
    assert _sites_in_source(_ORDINARY_LUA, "ordinary.py") == []
