# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend scrape target depends on topology (#14315, #13765).

Prometheus reported `autobot-backend down — dial tcp <host>:8443: connection
refused`, so it had never collected a single backend series and #13765's cgroup
alerting had never had data to evaluate. The endpoint was never at fault: on the
uvicorn port it answers 200 and exports 120 `autobot_cgroup_memory` series
across 8 units, chromadb included.

The reason is that neither target is universally correct:

* uvicorn binds 127.0.0.1 only, so its port is reachable from the same host only.
* nginx on `backend_nginx_port` is the only LAN-facing entry — EXCEPT co-located,
  where #2829 tears that standalone vhost down because SLM's own nginx proxies
  to uvicorn directly.

So the original `:8443` was right for a distributed fleet and wrong on a
co-located host, and scraping `:8001` unconditionally would simply have inverted
which topology is broken — the same "connection refused", relocated.

These tests render the template for BOTH topologies rather than asserting on its
text, because the defect is which target each one produces.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_TEMPLATE = _ANSIBLE / "roles" / "monitoring" / "templates" / "prometheus.yml.j2"


def _render(**overrides) -> dict:
    """Render the scrape config with ansible-equivalent Jinja settings."""
    jinja2 = pytest.importorskip("jinja2")
    context = {
        "prometheus_port": 9090,
        "node_exporter_port": 9100,
        "groups": {"slm_nodes": []},
        "hostvars": {},
        "backend_port": 8001,
        "backend_nginx_port": 8443,
        "backend_host": "backend-node",
        "redis_host": "db-node",
    }
    context.update(overrides)
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, undefined=jinja2.ChainableUndefined)
    # `bool` is an Ansible filter, not stock Jinja2. Shimmed with Ansible's own
    # truthiness so the rendered result matches what a play produces — a test
    # that renders differently from ansible proves nothing about the template.
    env.filters["bool"] = lambda v: (
        str(v).strip().lower() in {"true", "yes", "on", "1"} if not isinstance(v, bool) else v
    )
    return yaml.safe_load(env.from_string(_TEMPLATE.read_text(encoding="utf-8")).render(**context))


def _backend_job(rendered: dict) -> dict:
    return next(j for j in rendered["scrape_configs"] if j["job_name"] == "autobot-backend")


def test_the_template_still_defines_a_backend_job():
    """Guard the guard: a rename makes every assertion below vacuous."""
    assert _backend_job(_render(slm_colocated_frontend=False))


def test_colocated_scrapes_uvicorn_on_loopback():
    """Co-located: #2829 removes the standalone nginx vhost, so the TLS front
    does not exist and uvicorn on loopback is the only reachable target. This is
    the case that was live-broken — `:8443` refused the connection."""
    job = _backend_job(_render(slm_colocated_frontend=True))
    assert job["scheme"] == "http"
    assert job["static_configs"][0]["targets"] == ["localhost:8001"]


def test_distributed_scrapes_the_tls_front():
    """Distributed: uvicorn is loopback-only on a REMOTE host, so its port is
    unreachable and nginx is the only LAN-facing entry. Scraping 8001 here would
    reproduce the original failure with the topologies swapped."""
    job = _backend_job(_render(slm_colocated_frontend=False))
    assert job["scheme"] == "https"
    assert job["static_configs"][0]["targets"] == ["backend-node:8443"]
    assert job["tls_config"]["insecure_skip_verify"] is True


def test_the_default_topology_is_the_distributed_one():
    """`slm_colocated_frontend` defaults to false, so an unset value must not
    silently select the loopback target on a remote backend."""
    job = _backend_job(_render())
    assert job["static_configs"][0]["targets"] == ["backend-node:8443"]


def test_neither_topology_targets_a_port_the_other_needs():
    """The two must not converge — that is the whole finding."""
    colocated = _backend_job(_render(slm_colocated_frontend=True))["static_configs"][0]["targets"]
    distributed = _backend_job(_render(slm_colocated_frontend=False))["static_configs"][0]["targets"]
    assert colocated != distributed, "both topologies resolve the same target — one of them is unreachable"


def test_the_mirrored_ports_have_not_drifted_from_the_backend_role():
    """The monitoring role runs against `slm_server` and the backend role
    against `backend`, so role defaults never cross and these values are
    duplicated by necessity. Duplication that nothing checks is how the original
    literal drifted to a port nothing binds."""
    monitoring = yaml.safe_load(
        (_ANSIBLE / "roles" / "monitoring" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    backend = yaml.safe_load((_ANSIBLE / "roles" / "backend" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    for key in ("backend_port", "backend_nginx_port"):
        assert monitoring[key] == backend[key], (
            f"{key} drifted: monitoring={monitoring[key]} backend={backend[key]}. "
            "The scrape config would target a port the service does not bind (#14315)."
        )


def test_the_rendered_config_is_valid_yaml_in_both_topologies():
    """Prometheus refuses its ENTIRE configuration if any part is malformed, so
    one broken scrape block silently removes every alert too."""
    for colocated in (True, False):
        rendered = _render(slm_colocated_frontend=colocated)
        assert "scrape_configs" in rendered
        assert all(j.get("job_name") for j in rendered["scrape_configs"])
