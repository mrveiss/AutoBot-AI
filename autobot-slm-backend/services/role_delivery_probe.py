# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Detect role-owned changes that never reached this host (#12959).

``update-all-nodes.yml`` — the playbook behind code-sync / self-update — deploys
components with inline tasks and applies exactly one role, and only a single
task file of it (``backend`` via ``tasks_from: env_only``). Anything that lives
in an Ansible role is therefore inert on every host updated through the builtin
path: the merge is green, the issue closes on that evidence, ``code_source``
carries the change, and the host never receives it.

Three issues were closed that way and later verified absent from a live host:
#12777 (faulthandler, ``roles/backend/templates``), #12886 (TTS streaming route,
``roles/tts-worker``) and #12907 (credential consolidation, ``roles/postgresql``).
Five self-update runs, each reaching ``ok=108``, moved none of them.

``test_update_all_applies_roles_12959.py`` already guards the *playbook* in CI.
That cannot see a host, so it stays green while a box silently runs undelivered
code. This module closes that half: it probes artifacts the roles are supposed
to own and reports the ones that are missing, feeding the same
``self_update_incomplete`` surface #12776 added rather than a parallel one.

Philosophy matches ``self_update_log_reader``: never raise, and treat *absent*
as "cannot verify" rather than as failure. A component that was never installed
on this box must not be reported as an undelivered update — crying wolf on a
fresh install is how a signal gets ignored.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Artifacts are small config/unit files; refuse to slurp anything unexpected.
MAX_ARTIFACT_BYTES = 256 * 1024

_UNIT_DIR = Path(os.getenv("SLM_SYSTEMD_UNIT_DIR", "/etc/systemd/system"))
_CREDENTIALS_DIR = Path(os.getenv("SLM_CREDENTIALS_DIR", "/etc/autobot"))

CONTAINS = "contains"
UNIQUE_KEY = "unique_key"


@dataclass(frozen=True)
class RoleInvariant:
    """One host-observable fact an Ansible role is responsible for placing."""

    role: str
    issue: str
    artifact: Path
    kind: str
    marker: str
    describes: str


def _deployed(component: str, *parts: str) -> Path:
    """Resolve a deployed component path via the canonical drift_checker helper."""
    from services.drift_checker import get_default_deployed_dir

    return Path(get_default_deployed_dir(component)).joinpath(*parts)


def invariants() -> list[RoleInvariant]:
    """The role-owned facts worth asserting after an update.

    Deliberately short. Each entry corresponds to an issue that was closed on
    merge evidence and later found absent from a live host, so every one of
    these would have fired at the time.
    """
    return [
        RoleInvariant(
            role="backend",
            issue="#12777",
            artifact=_UNIT_DIR / "autobot-backend.service",
            kind=CONTAINS,
            marker="PYTHONFAULTHANDLER",
            describes="backend unit lacks faulthandler, so a SIGABRT leaves no stack",
        ),
        RoleInvariant(
            role="tts-worker",
            issue="#12886",
            artifact=_deployed("autobot-tts-worker", "tts-worker.py"),
            kind=CONTAINS,
            marker="/tts/synthesize/stream",
            describes="TTS worker does not serve the streaming route the backend calls",
        ),
        RoleInvariant(
            role="postgresql",
            issue="#12907",
            artifact=_CREDENTIALS_DIR / "db-credentials.env",
            kind=UNIQUE_KEY,
            marker="AUTOBOT_DB_PASSWORD",
            describes="credential store still holds duplicate keys (stale copy first)",
        ),
    ]


@dataclass
class RoleDeliveryVerdict:
    """Which role-owned invariants this host fails, if any."""

    checked: int = 0
    skipped: int = 0
    undelivered: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def degraded(self) -> bool:
        return bool(self.undelivered)


def _read(path: Path) -> str | None:
    """Return *path*'s text, or None when absent/unreadable/oversized."""
    try:
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            logger.debug("role-delivery artifact too large to probe: %s", path)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _satisfied(inv: RoleInvariant, text: str) -> bool:
    """True when *text* meets *inv*."""
    if inv.kind == UNIQUE_KEY:
        pattern = re.compile(rf"^{re.escape(inv.marker)}=", re.MULTILINE)
        return len(pattern.findall(text)) <= 1
    return inv.marker in text


def probe_role_delivery(checks: list[RoleInvariant] | None = None) -> RoleDeliveryVerdict:
    """Report role-owned changes missing from this host (#12959).

    Never raises. An artifact that does not exist is *skipped*, not failed:
    absence means the component is not installed here, which is not the same as
    an update that failed to deliver.
    """
    verdict = RoleDeliveryVerdict()
    for inv in checks if checks is not None else invariants():
        text = _read(inv.artifact)
        if text is None:
            verdict.skipped += 1
            continue
        verdict.checked += 1
        if not _satisfied(inv, text):
            verdict.undelivered.append(f"{inv.role} ({inv.issue}): {inv.describes}")

    verdict.reason = _describe(verdict)
    if verdict.degraded:
        logger.error("role-delivery probe: %s", verdict.reason)
    return verdict


def _describe(v: RoleDeliveryVerdict) -> str:
    """Name what is undelivered, not just that something is."""
    if not v.checked:
        return "no role-owned artifacts present to verify"
    if not v.undelivered:
        return f"all {v.checked} role-owned invariant(s) satisfied"
    return (
        f"{len(v.undelivered)} of {v.checked} role-owned change(s) never reached this host "
        f"— the updater does not apply these roles (#12959): " + "; ".join(v.undelivered)
    )
