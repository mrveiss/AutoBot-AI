# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20484: a Redeploy runs on the node chosen, whatever the playbook's own hosts default is."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from api._role_procedure_vars import SLM_AGENT_PLAYBOOK, role_procedure_extra_vars

_BACKEND = Path(__file__).resolve().parent.parent
_ANSIBLE = _BACKEND / "ansible"
_HOSTS = re.compile(r"^\s*-?\s*hosts:\s*\"?\{\{\s*target_host\s*\|\s*default\('([^']+)'\)", re.MULTILINE)
_NODE = "00-SLM-Manager"


def _role(playbook: str = "deploy-monitoring.yml") -> SimpleNamespace:
    return SimpleNamespace(name="slm-monitoring", ansible_playbook=playbook)


def test_the_monitoring_redeploy_names_the_chosen_node() -> None:
    assert role_procedure_extra_vars(_role(), _NODE)["target_host"] == _NODE


def test_contrast_the_agent_playbook_keeps_its_own_switch() -> None:
    assert role_procedure_extra_vars(_role(SLM_AGENT_PLAYBOOK), _NODE)["slm_agent_run_common"] is False
    assert "slm_agent_run_common" not in role_procedure_extra_vars(_role(), _NODE)


def test_the_monitoring_play_does_read_target_host() -> None:
    """Control: the variable this passes is the one that decides where the play runs."""
    text = (_ANSIBLE / "deploy-monitoring.yml").read_text(encoding="utf-8")
    assert _HOSTS.search(text).group(1) == "localhost"


@pytest.mark.parametrize(
    "line", ["  hosts: \"{{ target_host | default('all') }}\"", "- hosts: {{ target_host | default('x') }}"]
)
def test_the_matcher_sees_both_hosts_spellings(line: str) -> None:
    assert _HOSTS.search(line)


def test_the_call_site_passes_the_node() -> None:
    text = (_BACKEND / "api/roles.py").read_text(encoding="utf-8")
    assert "extra_vars=role_procedure_extra_vars(role, target_node_id)," in text
