# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater applies the monitoring config, so the #16375 token pair lands (#18994).

The backend refuses ``/api/metrics/prometheus`` without the scrape token (#16375), and the
scraper side is written ONLY by ``roles/monitoring/tasks/prometheus_config.yml``: the token
file plus the ``prometheus.yml`` whose ``autobot-backend`` job names it. ``update-all-nodes.yml``
(code-sync / self-update, the only updater a GUI user reaches) never applied that role, so a
host updated through it kept its install-time config and every backend scrape returned 401.

Guarded here, narrowly:

* which plays reach a host that carries the monitoring role, with a contrast host that does not;
* that the task file those plays apply still writes BOTH halves of the pair -- the token file
  and the template -- and that the template still names the file and never a value;
* that the backend side of the pair (``backend.env``) is still rendered from the same variable.

Why this shape and not "every role must be applied": #12959's guard
(``test_update_all_applies_roles_12959.py``) already lists the managed roles; ``monitoring`` is
registered there too. This file adds the part that guard cannot see -- the host-group gate and
the content of the applied task file -- because applying the role under the wrong group, or
applying a task file that has lost the token write, is the same silent failure.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = pathlib.Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_MONITORING = _ANSIBLE / "roles" / "monitoring"
_BACKEND_ENV_TEMPLATE = _ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2"

# Group a node's monitoring role token maps to (services/inventory_builder.py _ROLE_TO_GROUPS).
_MONITORING_GROUP = "monitoring_vm"


def _plays() -> list[dict]:
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _monitoring_tasks_from(play: dict) -> set[str | None]:
    found: set[str | None] = set()
    for task in _walk(play.get("tasks") or []):
        include = task.get("ansible.builtin.include_role") or task.get("include_role")
        if isinstance(include, dict) and include.get("name") == "monitoring":
            found.add(include.get("tasks_from"))
    return found


def _play_matches(play: dict, host_groups: set[str]) -> bool:
    """True when the play's ``hosts`` pattern names one of the groups (plain group lists only)."""
    pattern = str(play.get("hosts", ""))
    return bool(set(pattern.replace(",", ":").split(":")) & host_groups)


def _monitoring_tasks_applied_to(host_groups: set[str]) -> set[str | None]:
    applied: set[str | None] = set()
    for play in _plays():
        if _play_matches(play, host_groups):
            applied |= _monitoring_tasks_from(play)
    return applied


def test_a_host_with_the_monitoring_role_gets_the_monitoring_config_tasks():
    applied = _monitoring_tasks_applied_to({_MONITORING_GROUP})
    assert "prometheus_config" in applied, (
        "update-all-nodes.yml no longer applies roles/monitoring prometheus_config to a host in "
        f"{_MONITORING_GROUP}: the scrape-token file and prometheus.yml stop reaching hosts updated "
        f"through the builtin updater (#18994). Applied to that group: {sorted(map(str, applied))}"
    )


@pytest.mark.parametrize(
    "groups",
    [{"redis", "database", "autobot"}, {"backend", "main", "infrastructure"}, {"npu_worker", "infrastructure"}],
    ids=["database-only", "backend-only", "npu-only"],
)
def test_a_host_without_the_monitoring_role_gets_none(groups):
    assert (
        _monitoring_tasks_applied_to(groups) == set()
    ), "a host that does not carry the monitoring role must not receive the monitoring tasks"


def test_the_updater_never_applies_the_monitoring_role_in_full():
    """Full application re-runs the install half and restarts Prometheus for no reason."""
    every = {t for play in _plays() for t in _monitoring_tasks_from(play)}
    assert None not in every and "main" not in every, f"monitoring applied in full: {sorted(map(str, every))}"


def _prometheus_config_tasks() -> list[dict]:
    return yaml.safe_load((_MONITORING / "tasks" / "prometheus_config.yml").read_text(encoding="utf-8"))


def test_the_applied_task_file_writes_both_halves_of_the_scrape_token_pair():
    tasks = _prometheus_config_tasks()
    writes_token_file = any(
        "prometheus_scrape_token_file" in str((t.get("ansible.builtin.copy") or {}).get("dest", ""))
        and "prometheus_scrape_token" in str((t.get("ansible.builtin.copy") or {}).get("content", ""))
        for t in tasks
    )
    renders_config = any((t.get("ansible.builtin.template") or {}).get("src") == "prometheus.yml.j2" for t in tasks)
    assert writes_token_file, "prometheus_config.yml no longer writes the scrape-token file (#16375)"
    assert renders_config, "prometheus_config.yml no longer renders prometheus.yml"


def test_an_empty_token_cannot_overwrite_a_working_token_file():
    copy_tasks = [t for t in _prometheus_config_tasks() if "ansible.builtin.copy" in t]
    assert copy_tasks and all("length > 0" in str(t.get("when", "")) for t in copy_tasks)
    assert all(t.get("no_log") is True for t in copy_tasks), "the token write must not print its value"


def test_the_template_names_the_token_file_and_never_a_value():
    text = (_MONITORING / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if "bearer_token_file:" in ln]
    assert lines and all(ln == "bearer_token_file: {{ prometheus_scrape_token_file }}" for ln in lines)
    assert "{{ prometheus_scrape_token }}" not in text and "{{ prometheus_scrape_token |" not in text


def test_the_backend_side_of_the_pair_is_still_rendered_from_the_same_variable():
    text = _BACKEND_ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "AUTOBOT_PROMETHEUS_SCRAPE_TOKEN" in text and "backend_prometheus_scrape_token" in text


def test_the_monitoring_play_keeps_a_deployed_token_when_the_fetch_degrades():
    play = next(p for p in _plays() if _play_matches(p, {_MONITORING_GROUP}) and _monitoring_tasks_from(p))
    includes = [
        str((t.get("ansible.builtin.include_tasks") or t.get("include_tasks") or ""))
        for t in _walk(play.get("tasks") or [])
    ]
    assert any("keep_prometheus_scrape_token.yml" in i for i in includes)
