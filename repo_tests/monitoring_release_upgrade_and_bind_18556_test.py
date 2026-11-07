# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Monitoring role: version bumps reinstall, and Alertmanager binds loopback (#18556 review).

1. The download/extract of Prometheus, Alertmanager and node_exporter was gated on
   ``stat.exists`` alone, so a ``*_version`` bump kept the old binary forever. The
   shared ``release_binary.yml`` decision is rendered here against a binary's real
   ``--version`` output shapes: missing or different -> install, equal -> no change.
2. ``alertmanager_listen_address`` followed ``monitoring_local_host``, a scrape-target
   name an operator may set to a routable address, exposing the unauthenticated
   silence API. It must be loopback by default and not derive from that variable.

**What this does not cover.** It renders the role's own expressions; it does not run
the play on a host.
"""

from __future__ import annotations

import ipaddress

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend/ansible/roles/monitoring"
_COMPONENTS = {  # task file -> (version var, restart handler)
    "prometheus.yml": ("prometheus_version", "Restart prometheus"),
    "alertmanager.yml": ("alertmanager_version", "Restart alertmanager"),
    "node_exporter.yml": ("node_exporter_version", "Restart node_exporter"),
}


def _tasks(name: str) -> list[dict]:
    return yaml.safe_load((_ROLE / "tasks" / name).read_text(encoding="utf-8")) or []


def _defaults() -> dict:
    return yaml.safe_load((_ROLE / "defaults/main.yml").read_text(encoding="utf-8"))


def _shared_vars() -> dict:
    """``inventory/group_vars/all.yml``: the one home of the monitoring address vars."""
    return yaml.safe_load((_ROLE.parents[1] / "inventory/group_vars/all.yml").read_text(encoding="utf-8"))


def _decide(exists: bool, stdout: str = "", stderr: str = "", version: str = "0.26.0") -> bool:
    (task,) = [t for t in _tasks("release_binary.yml") if "ansible.builtin.set_fact" in t]
    expr = task["ansible.builtin.set_fact"]["release_install_needed"]
    ctx = {
        "_release_binary_stat": {"stat": {"exists": exists}},
        "_release_binary_version": {"stdout": stdout, "stderr": stderr} if exists else {"skipped": True},
        "release_version": version,
    }
    return jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(expr).render(ctx).strip() == "True"


@pytest.mark.parametrize(
    ("exists", "stdout", "stderr", "needed"),
    [
        (False, "", "", True),  # fresh host
        (True, "alertmanager, version 0.25.0 (branch: HEAD, revision: x)", "", True),  # version bump
        (True, "", "alertmanager, version 0.25.0 (branch: HEAD)", True),  # older builds print to stderr
        (True, "alertmanager, version 0.26.01 (branch: HEAD)", "", True),  # prefix is not equality
        (True, "alertmanager, version 0.26.0 (branch: HEAD, revision: x)", "", False),  # contrast: equal
        (True, "", "alertmanager, version 0.26.0 (branch: HEAD)", False),  # contrast: equal on stderr
    ],
)
def test_release_install_decision(exists: bool, stdout: str, stderr: str, needed: bool) -> None:
    assert _decide(exists, stdout, stderr) is needed


@pytest.mark.parametrize("task_file", sorted(_COMPONENTS))
def test_install_is_gated_on_the_version_decision_and_restarts(task_file: str) -> None:
    version_var, handler = _COMPONENTS[task_file]
    tasks = _tasks(task_file)
    (inc,) = [t for t in tasks if t.get("ansible.builtin.include_tasks") == "release_binary.yml"]
    assert version_var in inc["vars"]["release_version"]
    fetch = [t for t in tasks if "ansible.builtin.get_url" in t or "ansible.builtin.unarchive" in t]
    assert len(fetch) == 2, f"{task_file}: expected one download and one extract, saw {len(fetch)}"
    assert all(t.get("when") == "release_install_needed | bool" for t in fetch), fetch
    (extract,) = [t for t in fetch if "ansible.builtin.unarchive" in t]
    assert handler in str(extract.get("notify")), f"{task_file}: a replaced binary must restart the service"


def test_alertmanager_binds_loopback_independent_of_monitoring_local_host() -> None:
    defaults = _defaults()
    bind = defaults["alertmanager_listen_address"]
    assert "monitoring_local_host" not in bind and "{{" not in bind, bind
    assert ipaddress.ip_address(bind).is_loopback
    # Contrast: an operator pointing the scrape-target name at a routable address
    # changes nothing about the bind, because the default does not reference it.
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    for local_host in (_shared_vars()["monitoring_local_host"], "192.0.2.10"):
        assert env.from_string(bind).render(monitoring_local_host=local_host) == bind
    unit = (_ROLE / "templates/alertmanager.service.j2").read_text(encoding="utf-8")
    assert "--web.listen-address={{ alertmanager_listen_address }}:" in unit


def test_prometheus_and_health_check_reach_alertmanager_on_its_bind() -> None:
    prom = (_ROLE / "templates/prometheus.yml.j2").read_text(encoding="utf-8")
    assert '"{{ alertmanager_listen_address }}:{{ alertmanager_port }}"' in prom
    (health,) = [t for t in _tasks("alertmanager.yml") if "ansible.builtin.uri" in t]
    assert health["ansible.builtin.uri"]["url"].startswith("http://{{ alertmanager_listen_address }}:")
