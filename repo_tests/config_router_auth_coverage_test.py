# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No config-registered router is ungated without being recorded (#16368).

The router-auth sweep read only ``core_routers.py``, so the routers the other
registries list were never checked, and ``api.skills`` sat among them
anonymous. This runs the same sweep over those registries, through
``config_router_auth``, with its own capped baseline. It is a sibling of
``router_auth_coverage_test.py`` rather than an edit to it.
"""

from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.config_router_auth import config_registered_routers, enumerate_config_routers

#: Config-registered routers with no gate of any detectable kind and no
#: documented open posture, frozen so that a NEW one fails. The list may only
#: SHRINK: remove an entry when its router gains a gate or a documented open
#: posture. Every entry is a finding tracked on #16375, which triages them by
#: exposure. None of them is an exemption.
KNOWN_UNGATED: frozenset[str] = frozenset(
    {
        "api.analytics_llm_patterns",
        "api.analytics_pattern_learning",
        "api.analytics_reporting",
        "api.anti_pattern",
        "api.captcha",
        "api.chat_knowledge",
        "api.code_search",
        "api.development_speedup",
        "api.diagnostics",
        "api.error_monitoring",
        "api.error_resilience",
        "api.knowledge_eval",
        "api.llm_awareness",
        "api.metrics",
        "api.natural_language_search",
        "api.phases",
        "api.project",
        "api.project_state",
        "api.prometheus_endpoint",
        "api.realtime_session",
        "api.registry",
        "api.rum",
        "api.search",
        "api.self_capabilities",
        "api.state_tracking",
        "api.system_validation",
        "api.validation_dashboard",
        "routers.code_completion",
        "routers.feedback",
        "routers.model_management",
    }
)

#: Config-registered routers this sweep cannot read, pinned so that a new one
#: fails rather than silently dropping out of every bucket. ``classify`` reads
#: ``<module>.py``; both of these are packages (``<module>/__init__.py``), so
#: whether they gate is not measured here. Tracked on #16375.
UNREADABLE: frozenset[str] = frozenset(
    {
        "api.codebase_analytics",
        "llc.api",
    }
)

REACH = declare(
    "config-router-auth-coverage",
    discover=config_registered_routers,
    floor=150,
    what="routers listed in the config router registries",
    growth=30,
)


def _ungated(root: Path) -> set[str]:
    return {v.module for v in enumerate_config_routers(root) if not v.gated and not v.intentional and not v.unreadable}


def test_the_sweep_reaches_every_config_registered_router() -> None:
    """Non-vacuity, bound to routers EXAMINED rather than routers found wanting."""
    routers = REACH.examined(repo_root())
    REACH.completed(len(routers))
    assert len(routers) >= 150


def test_the_skills_routers_are_gated() -> None:
    """#16368 exactly: the two routers that served anonymous callers must carry a gate."""
    verdicts = {v.module: v for v in enumerate_config_routers(repo_root())}
    for module in ("api.skills", "api.skills_hub"):
        assert verdicts[module].gated, f"{module} has no gate: {verdicts[module].evidence}"


def test_no_new_config_router_is_ungated_and_undocumented() -> None:
    new = sorted(_ungated(repo_root()) - KNOWN_UNGATED)
    assert not new, (
        "config-registered router(s) with no auth gate of any kind and no documented open posture:\n  "
        + "\n  ".join(new)
        + "\n\nGate it, or document the open posture IN THE FILE. This sweep does not model middleware."
    )


def test_the_known_ungated_list_has_not_gone_stale() -> None:
    fixed = sorted(KNOWN_UNGATED - _ungated(repo_root()))
    assert not fixed, "KNOWN_UNGATED entries that now have a gate -- remove them, the list only shrinks:\n  " + (
        "\n  ".join(fixed)
    )


def test_the_routers_this_sweep_cannot_read_are_declared() -> None:
    """A blind spot is a finding only while it is named: a new unreadable router must fail."""
    unreadable = {v.module: v.unreadable for v in enumerate_config_routers(repo_root()) if v.unreadable}
    assert set(unreadable) == UNREADABLE, f"unreadable config routers changed: {unreadable}"


def _plant(root: Path, module_source: str) -> None:
    """A tree with one router, listed only in ``feature_routers.py``."""
    registry = root / "autobot-backend" / "initialization" / "router_registry" / "feature_routers.py"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        'FEATURE_ROUTER_CONFIGS = [\n    ("api.planted", "/planted", ["planted"], "planted"),\n]\n', encoding="utf-8"
    )
    module = root / "autobot-backend" / "api" / "planted.py"
    module.parent.mkdir(parents=True)
    module.write_text(module_source, encoding="utf-8")


def test_a_planted_ungated_feature_router_is_caught(tmp_path: Path) -> None:
    """The guard can fail: the shape #16368 found, a feature router with no gate."""
    _plant(
        tmp_path,
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n"
        '@router.post("/run")\nasync def run():\n    return {}\n',
    )

    assert [(v.module, v.gated) for v in enumerate_config_routers(tmp_path)] == [("api.planted", False)]
    assert _ungated(tmp_path) == {"api.planted"}


def test_a_planted_gated_feature_router_passes(tmp_path: Path) -> None:
    """The control: the same router gated at router level, as #16368's fix does it."""
    _plant(
        tmp_path,
        "from fastapi import APIRouter, Depends\n\nfrom auth_middleware import get_current_user\n\n"
        "router = APIRouter(dependencies=[Depends(get_current_user)])\n\n\n"
        '@router.post("/run")\nasync def run():\n    return {}\n',
    )

    assert [(v.module, v.gated) for v in enumerate_config_routers(tmp_path)] == [("api.planted", True)]
