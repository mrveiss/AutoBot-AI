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

1. `client.set(key, value, nx=True)`, with or without `ex`/`px` in the same
   call -- create-if-absent is what makes a key a *claim* rather than a value,
   and the expiry may arrive in a separate `expire(...)` a line later. The TTL
   was required here at first, which left `set(nx=True)` + `expire(...)`
   invisible while the identical `setnx(...)` + `expire(...)` was caught: one
   spelling of a thing spelled several ways, the blind spot this file's own
   Lua arm exists to avoid.
2. `client.setnx(...)` / `msetnx(...)` -- the same lease under its older name.
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
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: Trees scanned. Frontend and infra are out of scope: a claim primitive is a
#: Redis call from Python.
_ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend", "scripts", "pipeline-scripts")

#: `redis.call('SET', ...)` inside a Lua script body.
#: `SETNX` as well as `SET` (review finding on #17380). A Lua script spelling
#: its acquisition `redis.call('SETNX', KEYS[1], ARGV[1])` with a separate
#: expiry is the same primitive, and the Python `setnx` arm cannot look inside
#: a string literal -- so that spelling was invisible to both arms at once.
#: Same one-spelling-of-several blind spot as the `set(nx=True)` + `expire()`
#: pair this matcher was widened for earlier in the same PR.
_LUA_SET = re.compile(r"redis\.call\(\s*['\"]SET(?:NX)?['\"]", re.I)

#: The tokens that turn such a SET into a lease acquire.
_LUA_LEASE_TOKEN = re.compile(r"['\"](EX|PX|NX)['\"]", re.I)

#: A separate expiry call in the same script. `SETNX` takes no expiry argument
#: -- the exclusivity is in the command name and the TTL arrives as its own
#: `PEXPIRE`/`EXPIRE` -- so requiring a quoted `'PX'` beside it demanded a shape
#: that spelling cannot have, which is the same blind spot as requiring `ex=`
#: in the Python `set(nx=True)` arm (review finding on #17380).
_LUA_EXPIRY_CALL = re.compile(r"redis\.call\(\s*['\"]P?EXPIRE(?:AT)?['\"]", re.I)

#: THE registry. Not an exemption -- the subject.
_THE_REGISTRY = "autobot_shared/coordination/work_claims.py"

#: Every file allowed to hold a claim-or-lock primitive, with HOW MANY it holds
#: and why. The count is the half a filename-only registry could not express
#: (review finding on #17380): a second primitive added to an already-listed
#: file was accepted, because the check asked "is this file allowed?" and never
#: "is this the primitive we allowed?".
#:
#: Bidirectional, per the repo's census rule: a count that GROWS fails as a new
#: unreviewed primitive, and a count that SHRINKS fails as a stale entry. The
#: old stale-entry check only fired when a file lost its LAST primitive, so
#: going from two to one was invisible in both directions at once.
_ALLOWED: dict[str, tuple[int, str]] = {
    "autobot-backend/events/channel_stream.py": (
        1,
        "#14815 — a watermark, not a lock: SETNX keeps the LOWEST broken event id for a channel.",
    ),
    "autobot-backend/llc/notifications/router.py": (
        1,
        "#8579 — one uvicorn worker runs the notification router.",
    ),
    "autobot-backend/llc/services/work_item_service.py": (
        2,
        "#8213 — an LLC *work item* checkout: product domain state, not agent coordination.",
    ),
    "autobot-backend/llc/sync/outbound_sync.py": (
        1,
        "#8521 — leader election for the LLC outbound sync loop.",
    ),
    "autobot-backend/services/feature_flags.py": (
        1,
        "#14866 -- a PERMANENT write-once provisioning, not a lease: the access-control enforcement mode is set with `nx` and NO expiry, so there is no holder, no renewal and nothing to lose a race for. Found by widening this arm to `set(nx=...)` without a TTL, which is the trade that widening makes: one invisible two-statement lease exchanged for one reasoned entry here.",
    ),
    "autobot-backend/services/gateway/ingest_governor.py": (
        1,
        "#14143 — inbound message dedup keyed by platform/channel/message id.",
    ),
    "autobot-backend/services/run_jwt.py": (
        1,
        "#7677 — a refreshed JTI's denylist entry, so an old token is one-use.",
    ),
    "autobot-backend/services/task_claim.py": (
        1,
        "#6468, documented as the one exception in #15957 — task IDENTITY, which a work scope is not.",
    ),
    "autobot-backend/utils/celery_reliability.py": (
        1,
        "#11607 — Celery task dedup by task id.",
    ),
    "autobot_shared/coordination/work_claims.py": (
        2,
        "#15947 — THE claim registry. Every agent scope claim goes through it.",
    ),
    "autobot_shared/idempotency.py": (
        2,
        "#15813 — an idempotency claim on a REQUEST, so a retry does not create twice. No owner, no renew.",
    ),
    "autobot_shared/leader_lease.py": (
        1,
        "#12842 — process leadership, not work scope: which replica runs a loop, not who owns a path.",
    ),
}

#: A floor on FINDINGS, kept as a matcher check and no longer the only one. The
#: repo's rule is that a vacuity floor binds to the sweep's REACH -- files
#: parsed, nodes visited -- never to the number of findings, because a sweep
#: that stops reading half the tree and still finds 12 primitives elsewhere
#: passes a findings floor (review finding on #17380). `REACH` below is that
#: bound; this stays as the separate assertion that the MATCHER still matches.
_MIN_SITES_SEEN = 12


def _iter_sources(root: Path | None = None) -> list[Path]:
    """Every module this guard sweeps. Empty on an empty tree, never raising --
    `_reach.declare`'s contract for a `discover` callable (#16154)."""
    root = root or repo_root()
    files: list[Path] = []
    for tree in _ROOTS:
        for path in sorted((root / tree).rglob("*.py")):
            # Relative to `root`, not `path.as_posix()` (review finding on
            # #17380). The absolute form carries the checkout's own location, so
            # a repo living under a directory called `tests` -- `/srv/tests/AutoBot-AI`
            # -- matched `/tests/` on EVERY module and excluded the entire sweep.
            # The floor tests would fail, but their message blames the matcher or
            # the reach, not the path filter, so the cause would be looked for in
            # the wrong place. Same family as an exclusion keyed on the wrong
            # path form silently covering nothing.
            relative = path.relative_to(root).as_posix()
            if "/tests/" in f"/{relative}" or path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            files.append(path)
    return files


#: The sweep's reach, declared so the meta-test proves the floor against the
#: live population (#15928) instead of this file asserting its own number.
#: Pinned MID-WINDOW, not at `population - growth`. With 3,001 modules live and
#: `growth=50`, a floor of 2,951 puts the slack exactly at the allowance, so the
#: very next module anyone adds reds the meta-test -- zero headroom by
#: construction (#17142). 2,976 leaves room for 25 more before a bump is due.
REACH = declare(
    "one-claim-registry",
    discover=_iter_sources,
    floor=2_976,
    what="Python modules swept for claim-or-lock primitives",
    growth=50,
)


def _sites_in_source(source: str, label: str) -> list[str]:
    """Every claim-or-lock primitive in one module, as `path:line kind`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            if name == "set" and "nx" in keywords:
                # The TTL is NOT required in the same call (review): a
                # `set(key, val, nx=True)` followed by a separate `expire(...)`
                # is the identical two-statement lease this guard already
                # catches when it is spelled `setnx`, and requiring `ex`/`px`
                # here left that one spelling invisible -- the exact
                # one-spelling-of-several blind spot #17363 was widened for.
                kind = "set-nx-ttl" if {"ex", "px"} & keywords else "set-nx"
                found.append(f"{label}:{node.lineno} {kind}")
            elif name in ("setnx", "msetnx"):
                found.append(f"{label}:{node.lineno} {name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _LUA_SET.search(node.value) and (
                _LUA_LEASE_TOKEN.search(node.value) or _LUA_EXPIRY_CALL.search(node.value)
            ):
                found.append(f"{label}:{node.lineno} lua-lease")
    return found


@lru_cache(maxsize=1)
def _sweep() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """One pass over the tree, shared: `(sites, unreadable)`.

    Cached because five tests called `_scan()` and one called `_unreadable()`,
    and each re-read and re-parsed every module under `_ROOTS` -- nearly 3,000
    files, six times over (review finding on #17380). That was most of this
    file's 127-second runtime, and it is exactly the cost that pushes a
    pre-push selection past its budget and blocks a push for a reason
    unrelated to the change being pushed.

    Safe to cache because nothing here mutates the tree, and the detector
    fixtures call `_sites_in_source` directly on inline sources rather than
    through the sweep -- so a cached result is never stale within a run.
    """
    root = repo_root()
    sites: list[str] = []
    blind: list[str] = []
    for path in _iter_sources():
        label = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            blind.append(f"{label} (not utf-8)")
            continue
        try:
            sites.extend(_sites_in_source(source, label))
        except SyntaxError as exc:
            blind.append(f"{label} (SyntaxError: {exc.msg})")
    return tuple(sites), tuple(blind)


def _unreadable() -> list[str]:
    """Modules the sweep could not parse, as `path (reason)`.

    Returned rather than swallowed (review finding on #17380). Both handlers
    below used to `continue`, so a module the sweep could not read contributed
    no findings and said nothing -- the sweep's own blind spots were
    indistinguishable from a clean file, which is the failure this guard exists
    to prevent applied to itself.
    """
    return list(_sweep()[1])


def _scan() -> list[str]:
    return list(_sweep()[0])


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


def test_every_exemption_holds_exactly_the_primitives_it_declares() -> None:
    """Bidirectional, per file: a growth and a shrink both fail (#17380 review).

    The previous version compared only the SET of filenames, so it caught a file
    that lost its LAST primitive and nothing else. Two failures hid in that gap,
    in opposite directions:

    - a developer adding a SECOND primitive to an already-listed file -- the
      check asked "is this file allowed?" and never "is this the primitive we
      allowed?", so an unreviewed lock landed inside an approved exemption;
    - a file going from two primitives to one -- a removal nobody reviewed
      either, and the stale check still passed because the file retained one.

    Three files hold two each today (`work_item_service.py`, `work_claims.py`,
    `idempotency.py`), so the gap was not hypothetical.
    """
    from collections import Counter

    actual = Counter(site.split(":", 1)[0] for site in _scan())

    drifted = [
        f"{path}: declares {declared}, found {actual.get(path, 0)}"
        for path, (declared, _reason) in sorted(_ALLOWED.items())
        if actual.get(path, 0) != declared
    ]

    assert not drifted, (
        "these exemptions no longer match what the file holds (#16653, #17380):\n  "
        + "\n  ".join(drifted)
        + "\nA HIGHER count is a new claim primitive inside an approved file -- review it and "
        "raise the number, or move it behind the registry. A LOWER count is a primitive that "
        "went away -- lower the number, or delete the entry when it reaches zero."
    )


def test_every_exemption_names_its_issue() -> None:
    """ "Why is this allowed" must be answerable without a git blame."""
    unexplained = sorted(path for path, (_count, reason) in _ALLOWED.items() if not re.search(r"#\d{4,5}", reason))

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


_PLANTED_SET_NX_NO_TTL = 'await client.set("lock:thing", "1", nx=True)\nawait client.expire("lock:thing", 30)\n'


def test_the_detector_catches_a_two_statement_lease() -> None:
    """`set(nx=True)` then `expire(...)` -- the spelling the first version missed."""
    sites = _sites_in_source(_PLANTED_SET_NX_NO_TTL, "planted.py")

    assert sites == ["planted.py:1 set-nx"], (
        "a create-if-absent write whose expiry arrives in the next statement is the same "
        "lease as `setnx` + `expire`, and must not be invisible because the TTL is not in "
        "the same call"
    )


def test_the_sweep_parses_every_module_it_reads() -> None:
    """Reach, not findings: the bound the repo's rule actually asks for.

    `test_the_scan_reaches_the_primitives_it_guards` asserts the MATCHER still
    matches. It cannot notice the sweep going blind: a scan that stops reading
    half the tree and still finds 12 primitives in the half it reads passes a
    findings floor while missing everything in the other half.
    """
    parsed = REACH.examined(repo_root())
    REACH.completed(len(parsed))

    # `REACH.floor`, not a second literal (review finding on #17380): the
    # declaration above already holds the number, and two copies are two things
    # to update. The repo's rule is that a vacuity floor binds to REACH.
    assert len(parsed) >= REACH.floor, (
        f"the sweep reached {len(parsed)} modules, expected at least {REACH.floor} -- it has stopped "
        "reading its subject, so every assertion above would pass by matching nothing"
    )


def test_the_sweep_has_no_blind_spots() -> None:
    """A module the sweep cannot parse is a finding, not a silent skip."""
    blind = _unreadable()

    assert not blind, (
        "the sweep could not read these modules, so any claim primitive in them is invisible "
        "to every assertion in this file:\n  " + "\n  ".join(blind[:10])
    )


def test_the_detector_catches_a_planted_lua_setnx() -> None:
    """`redis.call('SETNX', ...)` is the same primitive as `'SET'` with NX.

    The matcher required the literal `SET`, and the Python `setnx` arm cannot
    look inside a string -- so a Lua script spelling its acquisition `SETNX`
    was invisible to both arms at once (review finding on #17380).
    """
    source = 'SCRIPT = """\nif redis.call(\'SETNX\', KEYS[1], ARGV[1]) == 1 then\n  redis.call(\'PEXPIRE\', KEYS[1], ARGV[2])\nend\n"""\n'

    assert _sites_in_source(source, "planted.py"), "a Lua SETNX acquisition with a lease token must be caught"


def test_a_lua_setnx_without_a_lease_token_is_not_a_claim() -> None:
    """Negative control for the widened arm: NX alone is not a lease.

    Without this, the assertion above is satisfied by a matcher that flags every
    Lua script containing SETNX, which would make a watermark or a dedup key
    read as a lock.
    """
    source = 'SCRIPT = """redis.call(\'SETNX\', KEYS[1], ARGV[1])"""\n'

    assert not _sites_in_source(source, "planted.py")


def test_widening_the_lua_arm_did_not_narrow_it() -> None:
    """A plain `redis.call('SET', ...)` lease must still match.

    This is here because the first attempt at the widening wrote `SETNX?`,
    which makes only the `X` optional and therefore requires the `N` -- it
    stopped matching plain `SET` and the live site count fell from 15 to 12. A
    narrowing disguised as a widening, caught by re-measuring rather than by
    any test, so now a test holds it.
    """
    source = "SCRIPT = \"\"\"redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2])\"\"\"\n"

    assert _sites_in_source(source, "planted.py"), "the plain SET spelling stopped matching"
