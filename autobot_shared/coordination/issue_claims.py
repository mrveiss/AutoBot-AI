# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place "who is working on issue N" is answered (#17098, parent #16698).

Two parties claim GitHub issues: AutoBot's own dev loop (``dev_loop_issue_gate``) and the
developer sessions' machine-local ledger. They used to keep two registries, so neither could
refuse the other. This module is the integration point that makes ``work_claims`` -- the
``issue:<n>`` scope, ``autobot_shared/coordination/work_claims.py`` -- the single source of truth:
the ledger *writes through* to it for its ``issue`` kind and reads holders back from it. Every
other ledger kind (pr, branch, worktree, task) is untouched and stays ledger-local.

Interface (``python -m autobot_shared.coordination.issue_claims``; one JSON object on stdout)::

    claim   N --owner NAME [--note T] [--ttl-s S]   exit 0 granted/renewed, 1 held by someone else
    release N --owner NAME                           exit 0 released or not held, 1 held by another
    who     N                                        exit 0 (``held`` says whether anyone holds it)
    list                                             exit 0, every live issue claim

Exit 3 means the registry could not be read; exit 4 means the request itself was invalid (a
non-positive issue number, an empty owner, a TTL outside the registry's bounds). Any exit other
than 0 must be treated as a refusal
(fail closed -- a claim is never granted on a registry nobody could read). The refusal is logged
by exception class name, never with the exception text, which can carry connection details.

A session's claim is held under ``agent_id=<owner>``, ``task_id=SESSION_TASK_ID``. The dev loop
holds under its own agent id, so each side's holder is named in the other's refusal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from typing import Any

from redis.exceptions import RedisError

from autobot_shared.coordination.work_claims import (
    ClaimConflict,
    ClaimUnavailable,
    HolderError,
    ScopeError,
    WorkClaim,
    list_claims,
    release_scope,
    try_acquire,
)
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: How long a session's issue claim lives between ledger heartbeats. Mirrors the ledger's own
#: 4h default; the session re-runs ``claim`` to renew, so a crashed session frees the issue.
TTL_MIN_S, TTL_MAX_S = 60, 172800
SESSION_CLAIM_TTL_S = env_int_clamped("AUTOBOT_ISSUE_CLAIM_SESSION_TTL_S", 14400, min_v=TTL_MIN_S, max_v=TTL_MAX_S)

#: The task identity every session claim uses: one issue per session owner, reentrant on renew.
SESSION_TASK_ID = "dev-ledger"

#: 2 is argparse's own usage exit; 4 is an invalid request that parsed (bad number, owner or TTL).
EXIT_OK, EXIT_HELD, EXIT_UNREADABLE, EXIT_USAGE = 0, 1, 3, 4

#: What "the registry could not be read" looks like from here.
_UNREADABLE = (ClaimUnavailable, RedisError, OSError, asyncio.TimeoutError)


def issue_scope(number: int) -> str:
    """The ``work_claims`` scope string for GitHub issue *number*."""
    return f"issue:{number}"


def _holder(claim: WorkClaim) -> dict[str, Any]:
    keep = ("scope", "agent_id", "task_id", "intent", "acquired_at", "expires_at")
    return {k: v for k, v in asdict(claim).items() if k in keep}


async def claim_issue(number: int, owner: str, note: str = "", ttl_s: int | None = None) -> tuple[int, dict]:
    """Claim or renew *number* for *owner*; a different holder gets ``EXIT_HELD`` naming them."""
    result = await try_acquire(
        issue_scope(number),
        agent_id=owner,
        task_id=SESSION_TASK_ID,
        intent=note or f"dev session {owner}",
        ttl_s=SESSION_CLAIM_TTL_S if ttl_s is None else ttl_s,
    )
    if isinstance(result, ClaimConflict):
        return EXIT_HELD, {"held": True, "granted": False, "holder": _holder(result.holder), "message": str(result)}
    return EXIT_OK, {"held": True, "granted": True, "holder": _holder(result)}


async def release_issue(number: int, owner: str) -> tuple[int, dict]:
    """Release *owner*'s claim. Another holder's claim is never touched (``EXIT_HELD``)."""
    if await release_scope(issue_scope(number), agent_id=owner, task_id=SESSION_TASK_ID):
        return EXIT_OK, {"held": False, "released": True}
    code, body = await who_issue(number)
    if body["held"]:
        return EXIT_HELD, {**body, "released": False}
    return code, {**body, "released": False}


async def who_issue(number: int) -> tuple[int, dict]:
    """Who holds *number* right now; ``held: false`` only after the registry was actually read."""
    scope = issue_scope(number)
    for claim in await list_claims("issue"):
        if claim.scope == scope:
            return EXIT_OK, {"held": True, "holder": _holder(claim)}
    return EXIT_OK, {"held": False}


async def list_issue_claims() -> tuple[int, dict]:
    """Every live ``issue`` claim, for the ledger's ``claims`` view."""
    return EXIT_OK, {"claims": [_holder(c) for c in await list_claims("issue")]}


async def _dispatch(args: argparse.Namespace) -> tuple[int, dict]:
    if args.cmd == "claim":
        return await claim_issue(args.number, args.owner, args.note, args.ttl_s)
    if args.cmd == "release":
        return await release_issue(args.number, args.owner)
    if args.cmd == "who":
        return await who_issue(args.number)
    return await list_issue_claims()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="issue_claims", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "release", "who"):
        p = sub.add_parser(name)
        p.add_argument("number", type=int)
        if name != "who":
            p.add_argument("--owner", required=True)
        if name == "claim":
            p.add_argument("--note", default="")
            p.add_argument("--ttl-s", type=int, default=None)
    sub.add_parser("list")
    return parser


def _invalid_request(args: argparse.Namespace) -> str:
    """Why *args* can't be a valid request, or ``""``. Checked before the registry is touched."""
    if getattr(args, "number", 1) < 1:
        return f"issue number must be positive, got {args.number}"
    if hasattr(args, "owner") and not args.owner.strip():
        return "owner must not be empty"
    ttl = getattr(args, "ttl_s", None)
    if ttl is not None and not TTL_MIN_S <= ttl <= TTL_MAX_S:
        return f"--ttl-s must be within [{TTL_MIN_S}, {TTL_MAX_S}], got {ttl}"
    return ""


def run(argv: list[str]) -> tuple[int, dict]:
    """Parse *argv*, run it, and map every unreadable-registry failure to ``EXIT_UNREADABLE``."""
    args = _parser().parse_args(argv)
    invalid = _invalid_request(args)
    if invalid:
        return EXIT_USAGE, {"error": "bad-request", "message": invalid, "granted": False}
    try:
        return asyncio.run(_dispatch(args))
    except _UNREADABLE as exc:
        logger.error("issue claim registry unreadable (%s); refusing, nothing granted", type(exc).__name__)
        return EXIT_UNREADABLE, {"error": "registry-unreadable", "error_class": type(exc).__name__, "granted": False}
    except (HolderError, ScopeError) as exc:
        return EXIT_USAGE, {"error": "bad-request", "message": str(exc), "granted": False}


def main(argv: list[str] | None = None) -> int:
    code, body = run(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(json.dumps(body, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
