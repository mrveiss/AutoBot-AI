# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Render test for the backend unit's crash diagnostics (#12777).

autobot-backend SIGABRTs roughly every 25-55 minutes and leaves NO diagnostics
at all. Two things independently destroy the forensic trail:

  1. faulthandler was not enabled, so a fatal signal raised inside a C
     extension (uvloop / chromadb / torch-onnx, all compiled against a very new
     Python 3.14) unwinds without printing a Python stack — backend-error.log
     simply stops mid-stream and resumes at the next boot.
  2. Core capture is broken on the deployment platform: core_pattern pipes to
     /wsl-capture-crash, which does not exist, so the kernel reports
     code=dumped and the core is silently discarded.

Only (1) is fixable in this repo, and it is the prerequisite for diagnosing the
abort at all. This test pins it so a future unit-template edit cannot quietly
drop it and return the crash loop to being undiagnosable.

Follows the render-test precedent in test_pg_hba_multiuser.py (#10636).
"""

import os
from pathlib import Path

import pytest

jinja2 = pytest.importorskip("jinja2")

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "backend" / "templates"

_CTX = {
    "backend_install_dir": "/opt/autobot/autobot-backend",
    "backend_code_dir": "/opt/autobot/autobot-backend",
    "backend_log_dir": "/var/log/autobot",
    "backend_host": "0.0.0.0",
    "backend_port": 8001,
    "backend_workers": 1,
    "backend_user": "autobot",
    "backend_group": "autobot",
}


def _render(**overrides) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)))
    # `dirname` / `basename` are Ansible filters, not Jinja2 builtins — register
    # the stdlib equivalents so the real template renders outside Ansible.
    env.filters["dirname"] = os.path.dirname
    env.filters["basename"] = os.path.basename
    return env.get_template("autobot-backend.service.j2").render(**{**_CTX, **overrides})


def test_faulthandler_is_enabled():
    """Without this, a native abort prints nothing and cannot be diagnosed."""
    assert 'Environment="PYTHONFAULTHANDLER=1"' in _render()


def test_faulthandler_output_has_somewhere_to_land():
    """faulthandler writes to stderr, so the unit must still capture stderr.

    Enabling faulthandler while stderr goes nowhere would leave the crash just
    as invisible — the two settings only work as a pair.
    """
    rendered = _render()
    assert "StandardError=append:" in rendered
    assert "backend-error.log" in rendered


def test_restart_always_is_retained():
    """The crash loop is survivable only because systemd restarts the unit;
    the diagnostics change must not alter that."""
    assert "Restart=always" in _render()


# ---------------------------------------------------------------------------
# Core capture (#12777 item 2) — the other half of the destroyed forensic trail.
#
# This file previously asserted that only faulthandler was fixable here. That
# was wrong: ansible owns the host, so both the RLIMIT_CORE the unit grants and
# the kernel core_pattern are this repo's to set. What is genuinely NOT this
# role's call is flipping a host-wide setting by default, hence the opt-in.
# ---------------------------------------------------------------------------

_ROLE_DIR = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "backend"


def _yaml_text(relative: str) -> str:
    return (_ROLE_DIR / relative).read_text(encoding="utf-8")


def test_unit_grants_a_core_limit():
    """systemd defaults RLIMIT_CORE to 0 — without this no core is ever written."""
    assert "LimitCORE=" in _render()


def test_core_limit_is_overridable():
    """A node that must not write cores can cap it without editing the template."""
    assert "LimitCORE=0" in _render(backend_core_limit="0")


def test_core_capture_is_opt_in():
    """Rewriting kernel.core_pattern affects every process on the node."""
    defaults = _yaml_text("defaults/main.yml")

    assert "backend_core_capture: false" in defaults
    assert "backend_core_dir:" in defaults


def test_broken_core_handler_is_always_reported():
    """The failure mode is silence: code=dumped while the core is discarded.

    Detection must not be gated on the opt-in, or the state stays invisible on
    exactly the nodes that did not enable capture.
    """
    tasks = _yaml_text("tasks/core_capture.yml")
    report = tasks.split("Report that cores are being discarded")[1]

    assert "core_pattern" in tasks
    assert "not (backend_core_capture | default(false) | bool)" in report


def test_core_pattern_is_only_rewritten_when_enabled():
    """The sysctl write is the one genuinely invasive step — it must be gated."""
    tasks = _yaml_text("tasks/core_capture.yml")
    sysctl_task = tasks.split("Point core_pattern at a real path")[1]

    assert "kernel.core_pattern" in sysctl_task
    assert "when: backend_core_capture | default(false) | bool" in sysctl_task


def test_core_capture_tasks_are_wired_into_the_role():
    """An unincluded task file is dead code — the #12777 lesson twice over."""
    assert "core_capture.yml" in _yaml_text("tasks/main.yml")
