# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fleet security-posture auditor (GH#11224).

Recurring background job that reads the SLM node inventory and flags sensitive
services (datastores, admin dashboards, gateways) bound to a public / wildcard
interface rather than loopback. Findings are recorded as ``SecurityEvent`` rows
(metadata only — never secret values), so exposure regressions are surfaced
proactively instead of noticed reactively.

Uses the SLM's custom asyncio background-loop pattern (mirrors
``services/schedule_executor.py``), not Celery.
"""

import asyncio
import logging
import os
import uuid

from sqlalchemy import select

from models.database import Node, SecurityEvent, SecurityEventSeverity

logger = logging.getLogger(__name__)


def _get_session():
    """Return an async DB session context manager.

    ``db_service`` is imported lazily so importing this module does not pull in
    the ``services`` package ``__init__`` (and its ``autobot_shared`` auth chain),
    keeping the pure audit logic unit-testable in isolation.
    """
    from services.database import db_service

    return db_service.session()

# Poll interval — configurable per deployment; defaults to hourly.
_AUDIT_INTERVAL_SECONDS: int = int(os.getenv("SLM_SECURITY_AUDIT_INTERVAL_SECONDS", "3600"))

# Sensitive ports → (service label, SecurityEvent severity). Datastores and
# message brokers carry unauthenticated-data risk (HIGH); admin/observability
# dashboards are exposure-worthy but lower (MEDIUM). Expected-public ports
# (80/443/22) are intentionally absent.
SENSITIVE_PORTS: "dict[int, tuple[str, str]]" = {
    5432: ("postgresql", SecurityEventSeverity.HIGH.value),
    6379: ("redis", SecurityEventSeverity.HIGH.value),
    3306: ("mysql", SecurityEventSeverity.HIGH.value),
    27017: ("mongodb", SecurityEventSeverity.HIGH.value),
    9200: ("elasticsearch", SecurityEventSeverity.HIGH.value),
    5672: ("rabbitmq", SecurityEventSeverity.HIGH.value),
    8100: ("chromadb", SecurityEventSeverity.HIGH.value),
    11434: ("ollama", SecurityEventSeverity.HIGH.value),
    2375: ("docker-api", SecurityEventSeverity.CRITICAL.value),
    2376: ("docker-api-tls", SecurityEventSeverity.HIGH.value),
    9090: ("prometheus", SecurityEventSeverity.MEDIUM.value),
    3000: ("grafana", SecurityEventSeverity.MEDIUM.value),
    9120: ("slm-dashboard", SecurityEventSeverity.MEDIUM.value),
    9123: ("agent-dashboard", SecurityEventSeverity.MEDIUM.value),
}

_LOOPBACK_ADDRESSES = frozenset({"127.0.0.1", "::1", "localhost"})
_WILDCARD_ADDRESSES = frozenset({"0.0.0.0", "*", "::"})  # nosec B104 - detection allowlist, not a bind

# Module-level background-task state (mirrors schedule_executor.py).
_auditor_running = False
_auditor_task: "asyncio.Task | None" = None


def _is_public_address(address: "str | None") -> bool:
    """Return True when *address* is a non-loopback (externally reachable) bind.

    Conservative: an unknown/absent address (older agents predating GH#11224)
    returns False so we never raise a finding we can't substantiate.
    """
    if not address:
        return False
    addr = address.strip().lower()
    if addr in _WILDCARD_ADDRESSES:
        return True
    if addr in _LOOPBACK_ADDRESSES or addr.startswith("127."):
        return False
    # Any other concrete bound interface is reachable off-host.
    return True


def _scan_node_ports(listening_ports: "list | None") -> "list[dict]":
    """Return exposure findings for one node's ``listening_ports`` (GH#11224).

    A finding is raised only when a port is sensitive AND its bind address is
    public/wildcard. Each finding is a dict with port/address/service/severity.
    """
    findings: "list[dict]" = []
    for entry in listening_ports or []:
        if not isinstance(entry, dict):
            continue
        port = entry.get("port")
        classification = SENSITIVE_PORTS.get(port)
        if classification is None:
            continue
        address = entry.get("address")
        if not _is_public_address(address):
            continue
        label, severity = classification
        findings.append(
            {
                "port": port,
                "address": address,
                "service": label,
                "severity": severity,
                "process": entry.get("process"),
            }
        )
    return findings


def _build_security_event(node_id: str, finding: dict) -> SecurityEvent:
    """Construct a SecurityEvent row for an exposure *finding* (metadata only)."""
    port = finding["port"]
    service = finding["service"]
    address = finding["address"]
    return SecurityEvent(
        event_id=str(uuid.uuid4())[:16],
        event_type="port_exposure",
        severity=finding["severity"],
        category="network_exposure",
        source_node_id=node_id,
        target_node_id=node_id,
        target_resource=f"{address}:{port}",
        title=f"Sensitive port {port} ({service}) publicly exposed on {node_id}",
        description=(
            f"Service '{service}' is listening on {address}:{port} (non-loopback) on node "
            f"{node_id}. Confirm this exposure is intended and firewalled; bind to loopback "
            f"or restrict access if not."
        ),
        raw_data={
            "port": port,
            "address": address,
            "service": service,
            "process": finding.get("process"),
        },
    )


async def audit_fleet_security_posture() -> int:
    """Scan every node for publicly-exposed sensitive ports; record new findings.

    Deduplicates against unresolved ``port_exposure`` events per node so a
    standing exposure is not re-reported every cycle. Returns the count of newly
    created SecurityEvent rows.
    """
    new_events = 0
    async with _get_session() as db:
        nodes = (await db.execute(select(Node))).scalars().all()
        for node in nodes:
            findings = _scan_node_ports(node.listening_ports)
            if not findings:
                continue
            open_ports = await _open_exposure_ports(db, node.node_id)
            for finding in findings:
                if finding["port"] in open_ports:
                    continue
                db.add(_build_security_event(node.node_id, finding))
                new_events += 1
                logger.warning(
                    "Security posture: %s exposed on %s at %s:%s",
                    finding["service"],
                    node.node_id,
                    finding["address"],
                    finding["port"],
                )
    return new_events


async def _open_exposure_ports(db, node_id: str) -> "set[int]":
    """Return ports already flagged by an unresolved port_exposure event for *node_id*."""
    result = await db.execute(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "port_exposure",
            SecurityEvent.target_node_id == node_id,
            SecurityEvent.is_resolved.is_(False),
        )
    )
    return {e.raw_data.get("port") for e in result.scalars().all() if isinstance(e.raw_data, dict)}


async def _auditor_loop() -> None:
    """Background loop that runs the fleet audit every interval."""
    global _auditor_running
    logger.info("Security-posture auditor started (interval=%ss)", _AUDIT_INTERVAL_SECONDS)
    _auditor_running = True
    while _auditor_running:
        try:
            created = await audit_fleet_security_posture()
            if created > 0:
                logger.info("Security-posture audit raised %d new finding(s)", created)
        except Exception as e:  # never let a bad cycle kill the loop
            logger.error("Security-posture audit cycle failed: %s", e)
        await asyncio.sleep(_AUDIT_INTERVAL_SECONDS)
    logger.info("Security-posture auditor stopped")


def start_security_posture_auditor() -> None:
    """Start the auditor background task (call during application startup)."""
    global _auditor_task
    if _auditor_task is not None and not _auditor_task.done():
        logger.warning("Security-posture auditor already running")
        return
    _auditor_task = asyncio.create_task(_auditor_loop())
    logger.info("Security-posture auditor background task created")


def stop_security_posture_auditor() -> None:
    """Stop the auditor background task (call during application shutdown)."""
    global _auditor_running
    _auditor_running = False
    if _auditor_task is not None and not _auditor_task.done():
        _auditor_task.cancel()
        logger.info("Security-posture auditor stop requested")
