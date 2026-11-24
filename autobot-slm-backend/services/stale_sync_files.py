# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stale code-sync files of a node: list them, propose their removal, remove only what a human approved (#22033).

``list_stale_files`` is read-only. ``propose_cleanup`` files one ``destructive_action`` proposal per old sync
location in the backend's approval queue (#17038) through ``call_main_backend``; if the backend is down nothing
is proposed. ``remove_approved`` runs only when the backend's executor calls it after a human approved: fresh
listing, intent audit row, then the claim (the backend verifies a human decided it for this node and spends it
once), then removal of the approved files that are still stale and still byte-identical. Order follows
``node_ssh_password.delete_stored_password`` (#20046): no audit row, no claim; no claim, no removal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_stale_file_actions import (
    CLAIM_PATH_TEMPLATE,
    MAX_FILES_PER_PROPOSAL,
    PROPOSAL_PATH,
    STALE_SYNC_FILES_CLEANUP,
    api_relative,
)
from models.database import Node, NodeRole
from services import stale_sync_audit as audit
from services.git_subprocess import run_git_capture
from services.git_tracker import DEFAULT_REPO_PATH
from services.main_backend_client import call_main_backend
from services.node_ssh_key_probe import key_auth_and_sudo_work
from services.role_registry import DEFAULT_ROLES
from services.stale_sync_remote import remove_files, stat_candidates
from services.stale_sync_targets import (
    KeptFile,
    RoleSource,
    StaleFile,
    StaleListingError,
    candidates,
    classify,
    historical_blobs,
    moved_role_sources,
)

logger = get_logger(__name__)

NODE_NOT_FOUND = "Node not found"


class StaleRefused(Exception):
    """The operation may not proceed; ``status_code`` is what the route answers."""

    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


@dataclass
class StaleListing:
    """What a node holds under its old sync targets; ``error`` set means nothing is offered."""

    node_id: str
    commit: str | None = None
    stale: list[StaleFile] = field(default_factory=list)
    kept: list[KeptFile] = field(default_factory=list)
    error: str | None = None


async def _load_node(db: AsyncSession, node_id: str) -> Node:
    node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
    if node is None:
        raise StaleRefused(404, NODE_NOT_FOUND)
    return node


async def _sources_on(db: AsyncSession, node_id: str) -> list[RoleSource]:
    """The moved roles assigned to the node."""
    rows = (await db.execute(select(NodeRole.role_name).where(NodeRole.node_id == node_id))).scalars().all()
    assigned = set(rows)
    return [source for source in moved_role_sources(DEFAULT_ROLES) if source.role in assigned]


def _protected_dirs() -> list[str]:
    """Directories the corrected sync and code_source own now: nothing inside them is ever a stale copy."""
    return [str(role["target_path"]) for role in DEFAULT_ROLES if role.get("target_path")] + [DEFAULT_REPO_PATH]


async def _scan_location(
    node: Node, old_target: str, sources: list[RoleSource]
) -> tuple[list[StaleFile], list[KeptFile]]:
    """Stale and kept files under one old target, for every moved role that synced into it."""
    histories, wanted, kept = {}, {}, []
    for source in sources:
        histories[source.role] = await historical_blobs(DEFAULT_REPO_PATH, source.pathspec)
        wanted[source.role], refused = candidates(source, histories[source.role], _protected_dirs())
        kept += refused
    present = await stat_candidates(node, old_target, sorted({rel for rels in wanted.values() for rel in rels}))
    stale: dict[str, StaleFile] = {}
    for source in sources:
        found, other = classify(
            source, [p for p in present if p.rel in set(wanted[source.role])], histories[source.role]
        )
        stale.update({item.path: item for item in found if item.path not in stale})
        kept += other
    return sorted(stale.values(), key=lambda item: item.path), [k for k in kept if k.path not in stale]


async def list_stale_files(db: AsyncSession, node_id: str) -> StaleListing:
    """Read-only: the node's stale files, or a listing carrying ``error`` when it cannot be trusted."""
    node = await _load_node(db, node_id)
    listing = StaleListing(node_id)
    sources = await _sources_on(db, node_id)
    try:
        for old_target in sorted({source.old_target for source in sources}):
            stale, kept = await _scan_location(node, old_target, [s for s in sources if s.old_target == old_target])
            listing.stale += stale
            listing.kept += kept
        listing.commit = (await run_git_capture(DEFAULT_REPO_PATH, "rev-parse", "HEAD"))[0].strip() or None
    except StaleListingError as exc:
        return StaleListing(node_id, error=str(exc))
    return listing


def _file_json(item: StaleFile) -> dict[str, Any]:
    return {
        "path": item.path,
        "size_bytes": item.size_bytes,
        "modified_at": item.modified_at.isoformat(),
        "blob": item.blob,
    }


def _by_location(listing: StaleListing) -> dict[str, list[StaleFile]]:
    groups: dict[str, list[StaleFile]] = {}
    for item in listing.stale:
        groups.setdefault(item.old_target, []).append(item)
    return groups


async def _post_proposal(node_id: str, commit: str, old_target: str, found: list[StaleFile]) -> dict[str, Any]:
    """One proposal for one old sync location: the first ``MAX_FILES_PER_PROPOSAL`` files, never a shortened path."""
    body = {
        "node_id": node_id,
        "old_target": old_target,
        "commit": commit,
        "files": [_file_json(item) for item in found[:MAX_FILES_PER_PROPOSAL]],
        "total_found": len(found),
    }
    response = await call_main_backend(
        "POST",
        api_relative(PROPOSAL_PATH),
        content=json.dumps(body).encode("utf-8"),
        content_type="application/json",
        service="Stale file cleanup",
    )
    if response.status_code != 201:
        raise StaleRefused(
            409 if response.status_code == 409 else 502, f"the backend answered HTTP {response.status_code}"
        )
    return {**response.json(), "old_target": old_target, "proposed": len(body["files"]), "total_found": len(found)}


async def propose_cleanup(db: AsyncSession, node_id: str, actor: str | None) -> list[dict[str, Any]]:
    """File one proposal per old sync location holding stale files; nothing is proposed when none, or when the
    audit trail or the backend is unavailable (fail closed)."""
    listing = await list_stale_files(db, node_id)
    if listing.error:
        raise StaleRefused(409, listing.error)
    groups = _by_location(listing)
    if not groups:
        return []
    await _record(actor, node_id, audit.PHASE_PROPOSED, locations=sorted(groups), stale=len(listing.stale))
    return [await _post_proposal(node_id, listing.commit or "", target, found) for target, found in groups.items()]


async def _record(actor: str | None, node_id: str, phase: str, outcome: str = audit.SUCCESS, **details: Any) -> None:
    """The audit entry that must exist first; its absence is a 503 and nothing else happens."""
    try:
        await audit.record_cleanup_step(actor=actor, node_id=node_id, outcome=outcome, phase=phase, **details)
    except audit.StaleFileAuditUnavailable as exc:
        raise StaleRefused(503, "the audit trail is unavailable, so nothing was done") from exc


@dataclass(frozen=True)
class Approved:
    """What a spent approval authorizes: one old target and the files a human reviewed."""

    old_target: str
    files: list[dict[str, Any]]


async def _claim(approval_id: str, node_id: str) -> Approved:
    """Have the backend verify the approval is a human's, for this node, and unused -- and spend it."""
    response = await call_main_backend(
        "POST",
        api_relative(CLAIM_PATH_TEMPLATE.format(approval_id=approval_id)),
        content=json.dumps({"action": STALE_SYNC_FILES_CLEANUP.name, "node_id": node_id}).encode("utf-8"),
        content_type="application/json",
        service="Stale file cleanup",
    )
    if response.status_code != 200:
        raise StaleRefused(403 if response.status_code == 403 else 503, "the approval does not authorize this removal")
    data = response.json()
    return Approved(str(data["old_target"]), list(data["files"]))


def _still_stale(approved: Approved, fresh: StaleListing) -> tuple[list[StaleFile], list[dict[str, Any]]]:
    """The approved files the fresh listing still offers (same path and blob), and those it no longer does."""
    current = {(item.old_target, item.path, item.blob): item for item in fresh.stale}
    keep, gone = [], []
    for entry in approved.files:
        item = current.get((approved.old_target, entry["path"], entry["blob"]))
        (keep if item else gone).append(item or entry)
    return keep, gone


def _report(approved: Approved, gone: list[dict[str, Any]], results: dict[str, str]) -> list[dict[str, str]]:
    rows = [{"old_target": approved.old_target, "path": entry["path"], "result": "no_longer_stale"} for entry in gone]
    return rows + [
        {"old_target": approved.old_target, "path": path, "result": res} for path, res in sorted(results.items())
    ]


async def _claim_still_stale(
    actor: str, node_id: str, approval_id: str, fresh: StaleListing
) -> tuple[Approved, list[StaleFile], list[dict[str, Any]]]:
    """Spend the approval, then split its files into those still stale and those no longer offered.

    A refused claim leaves a denied completion row and removes nothing. A file whose old target is absent from
    the fresh listing is in neither list of the fresh set, so it lands in ``gone`` and is never removed.
    """
    try:
        approved = await _claim(approval_id, node_id)
    except StaleRefused as refusal:
        await _finish(actor, node_id, approval_id, audit.DENIED, reason=refusal.reason)
        raise
    keep, gone = _still_stale(approved, fresh)
    return approved, keep, gone


async def _after_ssh_failure(
    db: AsyncSession, node_id: str, approved: Approved, keep: list[StaleFile]
) -> dict[str, Any]:
    """What is known after ssh died mid-removal: some of *keep* may already be gone, so look again.

    The re-listing is itself best effort; when it fails the remainder is unknown, which is said, not guessed.
    """
    try:
        again = await list_stale_files(db, node_id)
    except (StaleRefused, StaleListingError):
        again = StaleListing(node_id, error="the node could not be listed again")
    if again.error:
        return {"outcome": "unknown", "may_have_removed": len(keep), "remaining": None}
    still = {item.path for item in again.stale if item.old_target == approved.old_target}
    remaining = sorted(item.path for item in keep if item.path in still)
    return {"outcome": "unknown", "may_have_removed": len(keep) - len(remaining), "remaining": remaining}


async def remove_approved(db: AsyncSession, node_id: str, approval_id: str) -> list[dict[str, str]]:
    """Remove the files a human approved, only where they are still stale; raises ``StaleRefused``."""
    node = await _load_node(db, node_id)
    if node.auth_method != "key" or not await key_auth_and_sudo_work(node):
        raise StaleRefused(409, "key access to the node is not proven")
    fresh = await list_stale_files(db, node_id)
    if fresh.error:
        raise StaleRefused(409, fresh.error)
    actor = f"approval:{approval_id}"
    await _record(actor, node_id, audit.PHASE_INTENT, approval_id=approval_id, stale=len(fresh.stale))
    approved, keep, gone = await _claim_still_stale(actor, node_id, approval_id, fresh)
    try:
        results = await remove_files(node, approved.old_target, keep)
    except StaleListingError as exc:
        known = await _after_ssh_failure(db, node_id, approved, keep)
        await _finish(actor, node_id, approval_id, audit.FAILED, error=str(exc), **known)
        raise StaleRefused(
            502, f"{exc}; outcome unknown, {known['may_have_removed']} file(s) may have been removed"
        ) from exc
    report = _report(approved, gone, results)
    removed = sum(r["result"] == "removed" for r in report)
    await _finish(actor, node_id, approval_id, audit.SUCCESS, removed=removed, results=report)
    return report


async def _finish(actor: str, node_id: str, approval_id: str, outcome: str, **details: Any) -> None:
    """The completion row; the approval is already spent, so a failed write is logged loudly, never raised."""
    try:
        await audit.record_cleanup_step(
            actor=actor,
            node_id=node_id,
            outcome=outcome,
            phase=audit.PHASE_FINISHED,
            approval_id=approval_id,
            **details,
        )
    except audit.StaleFileAuditUnavailable:
        logger.error(
            "Completion audit row for node %s under approval %s could not be written; intent row stands",
            node_id,
            approval_id,
        )


__all__ = ["StaleListing", "StaleRefused", "list_stale_files", "propose_cleanup", "remove_approved"]
