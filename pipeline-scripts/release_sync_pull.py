# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Which open pull request is the release sync: one definition, two readers (#16246, #16272).

``release_sync_main.py`` opens and updates the sync PR, and
``ci_dispatch_watchdog.py`` releases its parked runs. Both must agree on which PR
that is, so the rule lives here. This module imports neither of them: the sync
tool already imports the watchdog, so the watchdog importing the sync tool would
be a cycle.

A sync PR comes from THIS repository, from one of the named heads, into the
named base. A fork's branch of the same name never qualifies, and no other PR
into the base is ever selected.
"""

from __future__ import annotations

from typing import AbstractSet, Any, Dict, List, Protocol

#: The branch sync-main-to-dev.yml force-pushes Dev_new_gui to and opens the PR from.
RELEASE_SYNC_HEAD = "release-sync-main"
RELEASE_SYNC_BASE = "main"


class PullLister(Protocol):
    """The slice of the watchdog's API client this module needs."""

    repository: str

    def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
        """Open PRs into *base*. Raises on an unusable answer; never returns a guess."""


def is_sync_pull(pull: Dict[str, Any], repository: str, heads: AbstractSet[str], base: str) -> bool:
    """True for an open pull request from one of this repository's *heads* into *base*.

    A fork's branch can carry the same name, so the head repository is checked as
    well as the ref — a fork's pull request is never treated as the sync.
    """
    head_info = pull.get("head") or {}
    head_repo = (head_info.get("repo") or {}).get("full_name")
    base_ref = (pull.get("base") or {}).get("ref")
    return head_info.get("ref") in heads and head_repo == repository and base_ref == base


def release_sync_pulls(api: PullLister, swept_base: str) -> List[Dict[str, Any]]:
    """The open release-sync PR into ``main``, for a watchdog sweeping *swept_base* (#16272).

    At most one PR: GitHub allows one open PR per head and base. Empty when
    *swept_base* is already ``main``, because that sweep lists the PR itself. A
    listing error propagates: an unreadable listing is not "no sync PR open".
    """
    if swept_base == RELEASE_SYNC_BASE:
        return []
    pulls = api.open_pull_requests(RELEASE_SYNC_BASE)
    return [pull for pull in pulls if is_sync_pull(pull, api.repository, {RELEASE_SYNC_HEAD}, RELEASE_SYNC_BASE)]
