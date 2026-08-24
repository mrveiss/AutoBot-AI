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

# #13765: the two trees `systemctl set-property` writes into. NOTHING in this
# repo renders here — ansible's own drop-ins go to /etc/systemd/system/<unit>.d/
# — so every file under these roots is out-of-band by construction. That is the
# whole reason the scan can be unbounded rather than a list of units to keep in
# sync: the issue explicitly asks for every service, because
# `paperclip.service.d` was found alongside `autobot-backend.service.d`.
_CONTROL_ROOTS = tuple(
    Path(raw)
    for raw in os.getenv(
        "SLM_SYSTEMD_CONTROL_ROOTS",
        "/etc/systemd/system.control:/run/systemd/system.control",
    ).split(":")
    if raw
)

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
    #: Units running under memory limits their unit file does not declare
    #: (#13765). Kept separate from ``undelivered`` because the remedy differs:
    #: an undelivered role change needs a redeploy, an out-of-band override
    #: needs the drop-in retiring once the template carries the decision.
    out_of_band: list[str] = field(default_factory=list)
    #: False when the set-property trees could not be read, so ``out_of_band``
    #: being empty means "did not look", not "nothing there". None when the
    #: scan was not requested at all.
    out_of_band_observed: bool | None = None

    @property
    def degraded(self) -> bool:
        return bool(self.undelivered) or bool(self.out_of_band)


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


def probe_out_of_band_limits(control_roots: tuple[Path, ...] | None = None) -> tuple[list[str], bool]:
    """Units running under memory limits no repo artifact declares (#13765).

    Returns ``(unit names, observed)``. ``observed`` is False when the trees
    could not be read, and the caller must then report *skipped* rather than
    clean — an unreadable control tree looks exactly like an empty one, and
    "nothing found" is the reassuring answer this issue exists to distrust.

    A *missing* root is genuinely clean and says so: `systemctl set-property`
    creates the tree on first use, so its absence means no property override has
    ever been applied on this host. That is an observation, not an absence of
    evidence.

    `autobot-backend` ran for months under `MemoryHigh=8G` / `MemoryMax=12G`
    applied this way. Reading the role, the unit template or the repo gave no
    indication the limits existed, a fresh install of the same commit got none,
    and the state they produced — throttled, `STAT=D`, health timing out,
    systemd `active` — sent whoever investigated toward application code. That
    is the host-differs-from-repo condition this probe exists to catch.

    The predicate is imported from the metrics collector rather than
    reimplemented: `autobot_cgroup_memory_limits_out_of_band` answers the same
    question, and two definitions of "out-of-band" free to drift apart would
    make one surface contradict the other about the same unit. That collector's
    scope is also hard-won — it deliberately excludes
    `/etc/systemd/system/<unit>.d/`, where the redis role legitimately renders
    `MemoryLimit=`, and matches only properties that actually cap memory rather
    than any `Memory*=`.
    """
    roots = _CONTROL_ROOTS if control_roots is None else control_roots
    try:
        from autobot_shared.monitoring.metrics.cgroup_memory import has_out_of_band_limits
    except Exception as exc:  # noqa: BLE001 — never raise out of a status probe
        logger.warning("role-delivery: out-of-band check unavailable: %s", exc)
        return [], False

    units: set[str] = set()
    observed = False
    for root in roots:
        try:
            if not root.is_dir():
                # Never created => set-property has never run here. Observed.
                observed = True
                continue
            entries = sorted(root.iterdir())
        except OSError as exc:
            logger.warning("role-delivery: cannot read %s: %s", root, exc)
            continue
        observed = True
        for entry in entries:
            if not entry.name.endswith(".service.d"):
                continue
            unit = entry.name[: -len(".d")]
            if has_out_of_band_limits(unit, (root,)):
                units.add(unit)
    return sorted(units), observed


def probe_role_delivery(
    checks: list[RoleInvariant] | None = None,
    control_roots: tuple[Path, ...] | None = None,
) -> RoleDeliveryVerdict:
    """Report role-owned changes missing from this host (#12959, #13765).

    Never raises. An artifact that does not exist is *skipped*, not failed:
    absence means the component is not installed here, which is not the same as
    an update that failed to deliver.

    The #13765 out-of-band scan runs when this probes THE HOST — ``checks`` left
    at its default — or when ``control_roots`` is given explicitly. Passing a
    ``checks`` list means "evaluate exactly these", and having that quietly also
    walk the real ``/etc/systemd/system.control`` would make a unit test's
    verdict depend on the machine running it. That is not hypothetical here: the
    self-hosted runner is the very host whose out-of-band drop-in this issue was
    filed about, so the scan would have reddened unrelated assertions on one
    runner and passed on another.

    ``out_of_band`` is deliberately NOT folded into ``checked``/``skipped``.
    Those count role-owned invariants; an override is a different question with
    a different remedy, and merging them would have silently shifted every
    existing count assertion by one.
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

    if checks is None or control_roots is not None:
        verdict.out_of_band, verdict.out_of_band_observed = probe_out_of_band_limits(control_roots)

    verdict.reason = _describe(verdict)
    if verdict.degraded:
        logger.error("role-delivery probe: %s", verdict.reason)
    return verdict


def _describe(v: RoleDeliveryVerdict) -> str:
    """Name what is undelivered, not just that something is."""
    parts: list[str] = []
    if v.undelivered:
        parts.append(
            f"{len(v.undelivered)} of {v.checked} role-owned change(s) never reached this host "
            f"— the updater does not apply these roles (#12959): " + "; ".join(v.undelivered)
        )
    if v.out_of_band:
        parts.append(
            f"{len(v.out_of_band)} unit(s) run under memory limits their unit file does not "
            f"declare, applied out-of-band with `systemctl set-property` — a fresh install of "
            f"this commit would not reproduce them (#13765): " + ", ".join(v.out_of_band)
        )
    if v.out_of_band_observed is False:
        # Not degraded — an unreadable tree is not a finding. But it must not be
        # reported as a clean scan either: "found nothing" and "could not look"
        # are the same empty list, and reading one as the other is the defect
        # this probe exists to catch (#13765).
        parts.append("out-of-band memory overrides could not be checked on this host (#13765)")
    if parts:
        return "; ".join(parts)
    if not v.checked:
        return "no role-owned artifacts present to verify"
    return f"all {v.checked} role-owned invariant(s) satisfied"
