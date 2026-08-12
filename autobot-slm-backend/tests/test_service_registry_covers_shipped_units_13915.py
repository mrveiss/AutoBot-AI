# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every long-running AutoBot unit an ansible role ships is in the registry (#13915).

`_SERVICE_DEFINITIONS` is presented as the canonical registry of orchestrable
services and listed **2 of the 9** actually running — `autobot-backend` among the
missing. Nothing failed, because the orchestration API falls back to runtime
discovery; its own error message gives it away (*"node_id required for
**discovered** service"*). A canonical source can be missing most of the platform
and never raise.

The cost was paid elsewhere: #13539 (the updater hand-wrote a restart list that
omitted celery, which then served 7-day-old code across ten deploys) and #4090
(chromadb crash-looped 1681 times; no registry-driven sweep knew it existed).

This test is the mechanism the umbrella (#13916) asks every consolidation to ship:
one that **fails when a new copy appears** — here, when a role starts shipping a
service the registry does not know about.
"""

import importlib.util
import pathlib
import re

import pytest

_SLM_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ANSIBLE = _SLM_BACKEND / "ansible"


def _load_orchestrator():
    """Load the module by path rather than by package name.

    ``services`` exists in **both** ``autobot-backend`` and ``autobot-slm-backend``,
    so ``from services.service_orchestrator import ...`` resolves to whichever is
    first on the path — which under pytest is not this one. Two same-named
    packages is its own canonical-source problem; loading by path keeps this test
    honest about which registry it is checking.
    """
    path = _SLM_BACKEND / "services" / "service_orchestrator.py"
    spec = importlib.util.spec_from_file_location("_slm_service_orchestrator_13915", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SERVICE_DEFINITIONS = _load_orchestrator()._SERVICE_DEFINITIONS

# Units that are deliberately **not** orchestrable singletons. Recorded here with
# the reason rather than omitted, per the umbrella's second acceptance criterion —
# an unexplained exclusion is indistinguishable from an oversight.
_NOT_ORCHESTRABLE_SINGLETONS = {
    # Oneshot units driven by timers, not services to start/stop/health-check.
    "autobot-key-rotation": "oneshot, timer-driven",
    "autobot-pg-backup": "oneshot, timer-driven",
    # A systemd template unit: instantiated per bridge (`autobot-mcp-bridge@x`),
    # so there is no single instance for a registry entry to describe.
    "autobot-mcp-bridge@": "systemd template unit, instantiated per bridge",
    # A deployment variant of autobot-backend, not a service in its own right —
    # the two are never both running.
    "autobot-backend-single-worker": "single-worker variant of autobot-backend",
}


def _service_templates() -> dict:
    """Every ``*.service.j2`` an ansible role ships, by unit name."""
    found = {}
    for path in _ANSIBLE.rglob("*.service.j2"):
        found[path.name[: -len(".service.j2")]] = path
    return found


def _is_long_running(path: pathlib.Path) -> bool:
    """A unit systemd will keep alive — i.e. one worth orchestrating.

    ``Restart=`` is the discriminator: oneshots do not set it. Classifying by the
    file's own content rather than by a hand-kept list is the point, since a
    hand-kept list is the failure mode under repair.
    """
    text = path.read_text(encoding="utf-8")
    return re.search(r"^Restart=", text, re.M) is not None


def _registry_units() -> set:
    return {d.systemd_service for d in _SERVICE_DEFINITIONS.values() if d.systemd_service}


# ------------------------------------------------------------- the guard


def test_every_shipped_autobot_service_is_in_the_registry():
    """The check that converts a silent divergence into a failing build.

    Adding a role that ships ``autobot-something.service.j2`` without a registry
    entry fails here, instead of working fine for months via discovery and then
    surfacing as a stale worker or an unmonitored crash loop.
    """
    templates = _service_templates()
    shipped = {
        name
        for name, path in templates.items()
        if name.startswith("autobot-") and name not in _NOT_ORCHESTRABLE_SINGLETONS and _is_long_running(path)
    }

    missing = sorted(shipped - _registry_units())

    assert missing == [], (
        f"These units are shipped by an ansible role but absent from "
        f"_SERVICE_DEFINITIONS: {missing}. Add a ServiceDefinition, or record the "
        f"unit in _NOT_ORCHESTRABLE_SINGLETONS with the reason."
    )


def test_the_registry_names_no_unit_nobody_ships():
    """The other direction: an entry for a unit no role ships is equally wrong.

    ``autobot-agent`` was in the registry while not running on this host — the
    same divergence pointing the other way.
    """
    templates = set(_service_templates())
    # Third-party units (nginx, ollama, redis-stack-server) are managed by their
    # own packages and ship no template here; only autobot-* units are ours.
    ours = {u for u in _registry_units() if u.startswith("autobot-")}

    unshipped = sorted(ours - templates)

    assert unshipped == [], f"Registry names units no ansible role ships: {unshipped}"


# -------------------------------------------------- the specific regressions


@pytest.mark.parametrize(
    "unit,issue",
    [
        ("autobot-backend", "the primary service, absent from the canonical registry"),
        ("autobot-celery", "#13539: served 7-day-old code across ten deploys"),
        ("autobot-celery-beat", "#13539: same deploy path as celery"),
        ("autobot-chromadb", "#4090: crash-looped 1681 times unmonitored"),
        ("autobot-tts-worker", "absent while running"),
        ("autobot-ai-stack", "absent while running"),
    ],
)
def test_the_units_this_issue_found_missing_are_present(unit, issue):
    """Named individually so a regression says *which* service and why it mattered."""
    assert unit in _registry_units(), f"{unit} missing from the registry — {issue}"


def test_the_guard_would_notice_a_new_unregistered_service():
    """Guard the guard: prove the classification actually selects units.

    A `_is_long_running` that returned False for everything, or a glob that
    matched nothing, would make the test above pass vacuously forever.
    """
    templates = _service_templates()

    assert len(templates) > 20, f"the template glob found only {len(templates)} units"
    assert any(_is_long_running(p) for p in templates.values())
    assert not _is_long_running(templates["autobot-key-rotation"]), "oneshot misclassified as long-running"
    assert _is_long_running(templates["autobot-celery"]), "a Restart= unit read as oneshot"


def test_celery_declares_what_it_depends_on():
    """#13539's durable fix needs edges, not just membership.

    "Which services import the deployed tree and must restart after a sync?" is
    unanswerable from a flat list, which is why the updater hand-wrote one.
    """
    celery = _SERVICE_DEFINITIONS["celery"]

    assert "backend" in celery.dependencies
