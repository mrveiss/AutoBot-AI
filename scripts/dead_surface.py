# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Why a backend path has no frontend caller, and whether that is a defect (#16816).

``audit_api_wiring.py --dead-surface`` lists paths the frontend never reaches. Most
of them are reached correctly by something that is not a browser, so a bare count is
large, mostly benign, and gets dismissed on first read -- which is how the mode went
unused for the life of the script. Splitting it is what makes the number actionable.

Lives here rather than in the auditor because that file sits at its recorded size
ceiling, and a ceiling only ever goes down.
"""

import logging

logger = logging.getLogger(__name__)

_AGENT_FACING_PREFIXES = ("/api/agent/", "/api/llc/agent/", "/agent/")
_MACHINE_FACING_PREFIXES = ("/api/webhooks/", "/webhooks/", "/api/health", "/health", "/api/metrics", "/metrics")
_COMPANY_OS_MARKERS = ("/llc/", "/companies", "/work-items", "/boards", "/approvals", "/sprints", "/backlog")


def _is_company_os(path: str) -> bool:
    """Company OS surface, for the subtotal that answers 'can a user run the company'."""
    return any(m in path for m in _COMPANY_OS_MARKERS)


def classify_dead_surface(dead: list) -> dict:
    """Split paths with no frontend caller by whether a caller was ever expected (#16816).

    Three reasons a backend path has no frontend consumer, and only one of them
    is a defect:

    ``agent``    reached by an adapter or an agent's own API key, never by a browser.
    ``machine``  webhooks, health and metrics -- called by senders outside this repo.
    ``gui``      a capability that exists and no part of the UI can reach. The gap.

    Returning the split rather than a total is the point: the undifferentiated
    number is large, mostly benign, and therefore ignored.
    """
    out = {"agent": [], "machine": [], "gui": []}
    for path in dead:
        if path.startswith(_AGENT_FACING_PREFIXES):
            out["agent"].append(path)
        elif path.startswith(_MACHINE_FACING_PREFIXES):
            out["machine"].append(path)
        else:
            out["gui"].append(path)
    return out


def report_dead_surface(dead: list) -> None:
    """Print the split (#16816).

    The printing lives with the classification so the auditor calls one function:
    that file sits at its recorded size ceiling, and a ceiling only goes down.
    """
    b = classify_dead_surface(dead)
    gui = b["gui"]
    logger.info(f"\n== BACKEND PATHS WITH NO FRONTEND CONSUMER: {len(dead)} ==")
    logger.info(f"   agent-facing (adapters call these):  {len(b['agent'])}")
    logger.info(f"   machine-facing (webhooks, health):   {len(b['machine'])}")
    logger.info(f"   NO GUI PATH TO THIS CAPABILITY:      {len(gui)}")
    logger.info(f"     of which Company OS:               {len([d for d in gui if _is_company_os(d)])}")
    for d in gui[:100]:
        logger.info("  %s", d)
    if len(gui) > 100:
        logger.info("  ... and %d more", len(gui) - 100)
