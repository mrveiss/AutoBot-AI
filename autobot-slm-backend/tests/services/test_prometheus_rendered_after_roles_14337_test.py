# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""prometheus.yml is rendered after the roles it describes exist (#14337).

The monitoring role runs in Play 1 of `deploy-slm-manager.yml`, while the
backend (Phase 4a) and frontend (4b) roles run inside `provision-fleet-roles.yml`,
imported afterwards. The scrape targets depend on which of those landed on this
host — #14315 resolves the backend target by observing whether the unit is
installed and whether the standalone nginx vhost is gone — so on a first-ever
provisioning run that decision is made against a host where neither exists yet.

Nothing re-read it afterwards. The monitoring role appears in exactly one play,
with no handler or later task that renders the config again, so a first run left
prometheus scraping an address nothing answers and it stayed that way until an
operator redeployed monitoring by hand. That is how the deployed config came to
carry a target the backend never bound, and one job fewer than the template
defines.

These tests assert the ordering rather than the text: which play renders the
config, and whether it comes after the roles that decide what the config should
say.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "deploy-slm-manager.yml"
_ROLE_TASKS = _ANSIBLE / "roles" / "monitoring" / "tasks"
_CONFIG_TASKS = _ROLE_TASKS / "prometheus_config.yml"

_TEMPLATE = "prometheus.yml.j2"


def _plays() -> list[dict]:
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))


def _index_of_fleet_provisioning() -> int:
    for i, play in enumerate(_plays()):
        if str(play.get("import_playbook", "")).endswith("provision-fleet-roles.yml"):
            return i
    raise AssertionError("provision-fleet-roles.yml is no longer imported by deploy-slm-manager.yml")


def _renders_config(play: dict) -> bool:
    """Whether this play runs the monitoring config tasks, by role or by include."""
    for entry in play.get("roles", []) or []:
        name = entry.get("role") if isinstance(entry, dict) else entry
        if name == "monitoring":
            return True
    for task in play.get("tasks", []) or []:
        include = task.get("ansible.builtin.include_role") or task.get("include_role") or {}
        if include.get("name") == "monitoring" and include.get("tasks_from") == _CONFIG_TASKS.name:
            return True
    return False


def test_the_config_is_rendered_again_after_fleet_roles_are_provisioned():
    """The regression. Before this, the only render happened in Play 1."""
    fleet = _index_of_fleet_provisioning()
    later = [i for i, play in enumerate(_plays()) if _renders_config(play) and i > fleet]
    assert later, (
        "no play renders the prometheus config after provision-fleet-roles.yml. "
        "The first render decides the scrape topology against a host where the "
        "backend and frontend roles have not run yet (#14337)."
    )


def test_the_early_render_is_still_there():
    """The late pass is an addition, not a replacement.

    Prometheus must be installed and configured before fleet provisioning too —
    dropping the early render would leave the service without a config for the
    whole of that phase.
    """
    fleet = _index_of_fleet_provisioning()
    early = [i for i, play in enumerate(_plays()) if _renders_config(play) and i < fleet]
    assert early, "the monitoring role no longer runs before fleet provisioning"


def test_the_render_tasks_exist_in_one_place_only():
    """Both entry points include the same file rather than copying it.

    A second copy of a topology decision is exactly how the analytics scanner
    and the api-wiring gate came to disagree about the same question (#13582).
    """
    assert _CONFIG_TASKS.is_file(), f"{_CONFIG_TASKS.name} is missing"

    templating = []
    for task_file in sorted(_ROLE_TASKS.glob("*.yml")):
        tasks = yaml.safe_load(task_file.read_text(encoding="utf-8")) or []
        for task in tasks:
            spec = task.get("ansible.builtin.template") or task.get("template") or {}
            if spec.get("src") == _TEMPLATE:
                templating.append(task_file.name)
    assert templating == [_CONFIG_TASKS.name], f"{_TEMPLATE} is rendered from {templating}, expected one file"


def test_the_config_file_actually_resolves_the_topology():
    """Rendering without the detection would emit the template's own fallback.

    The template branches on `_backend_metrics_on_loopback`; a render pass that
    does not set it takes `default(false)` and produces the distributed target
    regardless of the host — the exact bug #14315 fixed, reintroduced by a
    second entry point that renders without deciding.
    """
    tasks = yaml.safe_load(_CONFIG_TASKS.read_text(encoding="utf-8"))
    sets_fact = [t for t in tasks if "_backend_metrics_on_loopback" in (t.get("ansible.builtin.set_fact") or {})]
    renders = [i for i, t in enumerate(tasks) if (t.get("ansible.builtin.template") or {}).get("src") == _TEMPLATE]
    assert sets_fact, "the config tasks do not resolve _backend_metrics_on_loopback"
    assert renders, "the config tasks do not render the template"
    assert tasks.index(sets_fact[0]) < renders[0], "the topology is resolved after the config that reads it"


def test_the_late_pass_does_not_reinstall_prometheus():
    """Scoped to the config tasks, not the whole role.

    Re-running the role would reinstall the binary and restart a service that is
    already up, for a config change the handler already covers.
    """
    fleet = _index_of_fleet_provisioning()
    for play in _plays()[fleet + 1 :]:
        if not _renders_config(play):
            continue
        assert not play.get("roles"), (
            f"play {play.get('name')!r} re-runs whole roles after fleet provisioning; " "include only the config tasks"
        )
