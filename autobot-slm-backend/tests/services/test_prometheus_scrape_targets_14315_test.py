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

Two layers are tested, because the fix has two halves that fail independently:

1. The template renders the right target for a given topology.
2. The ROLE resolves that topology for itself. Branching on a variable another
   role `set_fact`s makes the template correct only under a playbook that runs
   both roles; the targeted redeploy path runs `roles: [monitoring]` alone, and
   there the variable is simply undefined and the fallback fires. A template
   that is right about a value nobody supplies is the same silent-default shape
   this whole issue is about.

The detection expression is read out of the role's own task file and evaluated,
rather than restated here — a copy of the logic would keep passing after the
role stopped matching it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_ROLE = _ANSIBLE / "roles" / "monitoring"
_TEMPLATE = _ROLE / "templates" / "prometheus.yml.j2"
_TASKS = _ROLE / "tasks" / "prometheus.yml"

_TOPOLOGY_FACT = "_backend_metrics_on_loopback"


def _env():
    """A Jinja environment that renders the way an ansible play does."""
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, undefined=jinja2.ChainableUndefined)
    # `bool` is an Ansible filter, not stock Jinja2. Shimmed with Ansible's own
    # truthiness so the rendered result matches what a play produces — a test
    # that renders differently from ansible proves nothing about the template.
    env.filters["bool"] = lambda v: (
        str(v).strip().lower() in {"true", "yes", "on", "1"} if not isinstance(v, bool) else v
    )
    return env


def _render(**overrides) -> dict:
    """Render the scrape config with ansible-equivalent Jinja settings."""
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
    return yaml.safe_load(_env().from_string(_TEMPLATE.read_text(encoding="utf-8")).render(**context))


def _backend_job(rendered: dict) -> dict:
    return next(j for j in rendered["scrape_configs"] if j["job_name"] == "autobot-backend")


def _tasks() -> list[dict]:
    return yaml.safe_load(_TASKS.read_text(encoding="utf-8"))


def _module(task: dict, name: str) -> dict:
    """A task's arguments for *name*, accepting the short or FQCN spelling.

    Matching only `set_fact` would make every assertion below vacuous the moment
    someone writes `ansible.builtin.set_fact` — which is the spelling this role
    actually uses, and which is how the first draft of these tests silently
    found no tasks at all.
    """
    for key in (name, f"ansible.builtin.{name}"):
        if isinstance(task.get(key), dict):
            return task[key]
    return {}


def _detect(*, unit_exists: bool, vhost_exists: bool, **overrides) -> str:
    """Evaluate the role's OWN detection expression for a filesystem state.

    Returns the raw rendered string, exactly as ansible stores a folded-scalar
    `set_fact` — `"True"` / `"False"`, not a bool. Feeding that string onward to
    the template is the point: the round trip through a string is where a
    stock-Jinja truthiness check would quietly accept `"False"`.
    """
    task = next(t for t in _tasks() if _TOPOLOGY_FACT in _module(t, "set_fact"))
    context = {
        "_backend_unit": {"stat": {"exists": unit_exists}},
        "_backend_vhost": {"stat": {"exists": vhost_exists}},
    }
    context.update(overrides)
    return _env().from_string(_module(task, "set_fact")[_TOPOLOGY_FACT]).render(**context).strip()


def test_the_template_still_defines_a_backend_job():
    """Guard the guard: a rename makes every assertion below vacuous."""
    assert _backend_job(_render(**{_TOPOLOGY_FACT: False}))


def test_colocated_scrapes_uvicorn_on_loopback():
    """Co-located: #2829 removes the standalone nginx vhost, so the TLS front
    does not exist and uvicorn on loopback is the only reachable target. This is
    the case that was live-broken — `:8443` refused the connection."""
    job = _backend_job(_render(**{_TOPOLOGY_FACT: True}))
    assert job["scheme"] == "http"
    assert job["static_configs"][0]["targets"] == ["localhost:8001"]


def test_distributed_scrapes_the_tls_front():
    """Distributed: uvicorn is loopback-only on a REMOTE host, so its port is
    unreachable and nginx is the only LAN-facing entry. Scraping 8001 here would
    reproduce the original failure with the topologies swapped."""
    job = _backend_job(_render(**{_TOPOLOGY_FACT: False}))
    assert job["scheme"] == "https"
    assert job["static_configs"][0]["targets"] == ["backend-node:8443"]
    assert job["tls_config"]["insecure_skip_verify"] is True


def test_neither_topology_targets_a_port_the_other_needs():
    """The two must not converge — that is the whole finding."""
    colocated = _backend_job(_render(**{_TOPOLOGY_FACT: True}))["static_configs"][0]["targets"]
    distributed = _backend_job(_render(**{_TOPOLOGY_FACT: False}))["static_configs"][0]["targets"]
    assert colocated != distributed, "both topologies resolve the same target — one of them is unreachable"


def test_the_role_resolves_the_topology_before_rendering():
    """The template must never depend on a variable this role did not set.

    `deploy-monitoring.yml` runs `roles: [monitoring]` and nothing else — it is
    what the role registry invokes for a per-role redeploy, i.e. the normal way
    a fix like this one ships. Any variable another role `set_fact`s is
    undefined there, so a template branching on one silently takes its fallback
    and a co-located host regresses on every targeted update.
    """
    names = [t.get("name", "") for t in _tasks()]
    setters = [i for i, t in enumerate(_tasks()) if _TOPOLOGY_FACT in _module(t, "set_fact")]
    template_task = next(i for i, t in enumerate(_tasks()) if _module(t, "template").get("src") == "prometheus.yml.j2")
    assert (
        setters
    ), f"no task sets {_TOPOLOGY_FACT}; the template's branch would always take its default. Tasks: {names}"
    assert setters[0] < template_task, "the topology fact is resolved after the config that reads it is written"


def test_detection_selects_loopback_only_when_the_vhost_is_actually_gone():
    """The live co-located host: backend unit present, standalone vhost removed.

    Observed state, not a re-derivation. What decides reachability is whether
    the vhost is serving — inferring that from the flag that governed its
    teardown reintroduces the dependency on another role having run.
    """
    assert _detect(unit_exists=True, vhost_exists=False) == "True"


def test_detection_keeps_the_tls_front_while_the_vhost_still_serves():
    """Both present: the vhost is reachable and is the established target.

    Switching to loopback here would be a behaviour change on hosts that were
    never broken — the failure mode this fix exists to avoid inverting.
    """
    assert _detect(unit_exists=True, vhost_exists=True) == "False"


def test_detection_does_not_claim_loopback_when_no_backend_runs_here():
    """A monitoring-only host has neither. Loopback would be nothing at all."""
    assert _detect(unit_exists=False, vhost_exists=False) == "False"
    assert _detect(unit_exists=False, vhost_exists=True) == "False"


def test_a_colocated_frontend_does_not_imply_a_colocated_backend():
    """The SLM host carries the frontend role; the backend is on a remote node.

    `setup_wizard._apply_colocation_vars` sets `slm_colocated_frontend` whenever
    the SLM host carries the *frontend* role, and treats a co-located backend as
    a separate, nested condition — so the flag is true here while no backend is
    reachable on loopback at all. An earlier revision of this fix OR-ed the flag
    into the detection and would have pointed prometheus at nothing.

    Two decisions that look like one: where the frontend is served, and where
    the backend can be reached. The whole issue is what happens when those get
    collapsed.
    """
    assert _detect(unit_exists=False, vhost_exists=False, slm_colocated_frontend=True) == "False"


def test_the_flag_never_overrules_what_is_on_disk():
    """No value of `slm_colocated_frontend` may change the answer.

    The flag cannot be ahead of the filesystem either: provision-fleet-roles.yml
    runs Backend at Phase 4a, before Frontend at 4b, so by the time the flag can
    become true the backend role has already made its vhost decision.
    """
    for unit in (True, False):
        for vhost in (True, False):
            baseline = _detect(unit_exists=unit, vhost_exists=vhost)
            for flag in (True, False):
                assert _detect(unit_exists=unit, vhost_exists=vhost, slm_colocated_frontend=flag) == baseline, (
                    f"slm_colocated_frontend={flag} changed the verdict for "
                    f"unit={unit} vhost={vhost}; the flag answers a different question"
                )


def test_the_detection_result_survives_the_round_trip_into_the_template():
    """`set_fact` stores a folded scalar as the STRING "True"/"False".

    So the template's `| bool` is load-bearing: plain Jinja truthiness accepts
    `"False"` as true and would pin every host to the loopback target.
    """
    for unit, vhost, expected in ((True, False, "localhost:8001"), (True, True, "backend-node:8443")):
        resolved = _detect(unit_exists=unit, vhost_exists=vhost)
        assert isinstance(resolved, str)
        job = _backend_job(_render(**{_TOPOLOGY_FACT: resolved}))
        assert job["static_configs"][0]["targets"] == [expected], f"{resolved!r} resolved to the wrong target"


def test_the_mirrored_ports_have_not_drifted_from_the_backend_role():
    """The monitoring role runs against `slm_server` and the backend role
    against `backend`, so role defaults never cross and these values are
    duplicated by necessity. Duplication that nothing checks is how the original
    literal drifted to a port nothing binds."""
    monitoring = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
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
        rendered = _render(**{_TOPOLOGY_FACT: colocated})
        assert "scrape_configs" in rendered
        assert all(j.get("job_name") for j in rendered["scrape_configs"])
