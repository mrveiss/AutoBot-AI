#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the reach-floor staleness audit applies -- ONE definition for PR CI and the pre-board lane (#22147).

A floor the tree outgrew is stale, not lost: it fails where it is fixed (a merge train head, a merge
group, main's own push) and only warns elsewhere (#19282, #22110). ``ci.yml`` and
``dispatch-preboard-guards.yml`` both call this entry, so the lane judges a member head exactly as PR
CI does. Stdlib only: it runs before any environment is built.

The branch is ``GITHUB_HEAD_REF`` when set (a pull request), else the branch of ``GITHUB_REF`` (a push
or a ``workflow_dispatch``). The audit applies iff the branch starts with ``train-``, or the event is
``merge_group``, or the event is a ``push`` to ``refs/heads/main``.

Usage: ``python3 pipeline-scripts/reach_audit_scope.py`` appends ``AUTOBOT_REACH_AUDIT=1`` to
``$GITHUB_ENV`` when it applies; one notice line is printed either way.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

#: The variable ``repo_tests/_reach.py`` reads (its ``REACH_AUDIT_ENV``; a test asserts they are equal).
REACH_AUDIT_ENV = "AUTOBOT_REACH_AUDIT"
TRAIN_PREFIX = "train-"
MAIN_REF = "refs/heads/main"
_HEADS = "refs/heads/"


def branch_of(head_ref: str, ref: str) -> str:
    """The pull request's head branch, else the branch *ref* names (``""`` for a non-branch ref)."""
    if head_ref:
        return head_ref
    return ref[len(_HEADS) :] if ref.startswith(_HEADS) else ""


def audit_applies(event_name: str, head_ref: str, ref: str) -> bool:
    """True where a stale floor must fail: a train head, a merge group, or a push to main."""
    if branch_of(head_ref, ref).startswith(TRAIN_PREFIX):
        return True
    return event_name == "merge_group" or (event_name == "push" and ref == MAIN_REF)


def decide(environ: Mapping[str, str]) -> bool:
    """:func:`audit_applies` over the ``GITHUB_*`` variables of the running step."""
    return audit_applies(
        environ.get("GITHUB_EVENT_NAME", ""), environ.get("GITHUB_HEAD_REF", ""), environ.get("GITHUB_REF", "")
    )


def main(environ: Mapping[str, str] = os.environ) -> int:
    applies = decide(environ)
    target = environ.get("GITHUB_ENV", "")
    if applies and not target:
        sys.stderr.write("GITHUB_ENV is not set; cannot enable the reach-floor audit\n")
        return 1
    if applies:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{REACH_AUDIT_ENV}=1\n")
    state = "enforced" if applies else "warn-only"
    sys.stdout.write(f"reach-floor staleness audit: {state} (event={environ.get('GITHUB_EVENT_NAME', '')})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
