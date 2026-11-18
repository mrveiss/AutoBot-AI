# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Render tests for the logrotate hourly timer drop-in (#12783).

/etc/logrotate.d/autobot sets `maxsize 100M` specifically so a runaway log is
capped BEFORE the next daily run. That guarantee was never real: `maxsize` is
only evaluated when logrotate RUNS, and the stock timer is OnCalendar=daily. So
between 00:00 ticks a log grew unbounded and maxsize only decided WHETHER to
rotate at the daily tick, never WHEN — chromadb.log reached 737 MB, 7.4x the
cap, and was rotated having already blown past it.

Follows the render-test precedent in test_pg_hba_multiuser.py (#10636).
"""

import os
from pathlib import Path

import pytest

jinja2 = pytest.importorskip("jinja2")
yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_ROLE = _ANSIBLE / "roles" / "common"
_GROUP_VARS_ALL = _ANSIBLE / "inventory" / "group_vars" / "all.yml"


def _inventory_autobot() -> dict:
    """The `autobot` fact `group_vars/all.yml` supplies to every play (#18882).

    The logrotate template builds its log glob from `{{ autobot.base_dir }}`, so the
    render needs that variable. Read from the SSOT file rather than restated here, the
    same way test_cleanup_never_destroys_data_14856.py resolves it.
    """
    data = yaml.safe_load(_GROUP_VARS_ALL.read_text(encoding="utf-8"))
    assert "base_dir" in data.get("autobot", {}), f"{_GROUP_VARS_ALL} no longer defines autobot.base_dir"
    return data["autobot"]


def _render(template: str, **ctx) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_ROLE / "templates")))
    env.filters["dirname"] = os.path.dirname
    env.filters["basename"] = os.path.basename
    return env.get_template(template).render(**ctx)


def test_timer_override_runs_hourly():
    """Hourly evaluation is what makes the existing maxsize cap enforceable."""
    rendered = _render("logrotate-hourly-override.conf.j2")
    assert "[Timer]" in rendered
    assert "OnCalendar=hourly" in rendered


def test_timer_override_clears_the_vendor_oncalendar_first():
    """systemd ACCUMULATES list-valued settings across drop-ins.

    Without the empty `OnCalendar=` reset, the vendor `daily` value would remain
    alongside `hourly` and the timer would keep its daily tick too — the drop-in
    must REPLACE the schedule, not add to it.
    """
    rendered = _render("logrotate-hourly-override.conf.j2")
    lines = [ln.strip() for ln in rendered.splitlines() if ln.strip().startswith("OnCalendar=")]
    assert lines[0] == "OnCalendar=", f"first OnCalendar must be the reset, got {lines}"
    assert lines[1] == "OnCalendar=hourly"


def test_maxsize_cap_still_present_in_logrotate_config():
    """The drop-in only makes the cap enforceable — the cap itself must remain."""
    rendered = _render("autobot-logrotate.j2", autobot=_inventory_autobot())
    assert "maxsize 100M" in rendered
    # copytruncate is load-bearing: every unit writes with StandardOutput=append:
    # and holds the fd open, so a rename-based rotation would strand the writer.
    assert "copytruncate" in rendered


def test_runtime_log_glob_follows_the_install_root():
    """#18882: the runtime-log stanza is built from `autobot.base_dir`, so a different root moves it."""
    root = "/srv/autobot-render-test"
    rendered = _render("autobot-logrotate.j2", autobot={**_inventory_autobot(), "base_dir": root})
    assert f"{root}/logs/*.log {{" in rendered
    default = _inventory_autobot()["base_dir"]
    assert f"{default}/logs/*.log" not in rendered


def test_task_installs_dropin_and_notifies_a_real_handler():
    """A drop-in needs daemon-reload + timer restart, or the new cadence does
    not apply until the next boot."""
    tasks = yaml.safe_load((_ROLE / "tasks" / "logrotate.yml").read_text(encoding="utf-8"))
    handlers = yaml.safe_load((_ROLE / "handlers" / "main.yml").read_text(encoding="utf-8"))

    dropin = [t for t in tasks if "logrotate.timer.d" in str(t.get("ansible.builtin.template", ""))]
    assert dropin, "no task installs the timer drop-in"

    notified = {t["notify"] for t in tasks if t.get("notify")}
    handler_names = {h["name"] for h in handlers}
    assert notified, "drop-in task must notify a handler"
    assert notified <= handler_names, f"notify targets missing from handlers: {notified - handler_names}"
