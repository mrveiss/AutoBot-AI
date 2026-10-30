# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A backend whose LLM role is on another node calls that node, and a single node stays on loopback (#19861).

The wizard wrote host vars for 7 roles and neither LLM role, so every model call went to the backend's
own loopback and chat failed on first run. These run the shipped function and the shipped expressions.
"""

from __future__ import annotations

import importlib.util
import types

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_SLM = repo_root() / "autobot-slm-backend"
_ANSIBLE = _SLM / "ansible"
_LLM_IP = "fleet-llm"


def _llm_infra_vars():
    """The shipped module; loaded by path, as the suite's stubs may replace the services package."""
    spec = importlib.util.spec_from_file_location("_llm_placement_19861", _SLM / "services" / "llm_placement.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.config = types.SimpleNamespace(port=types.SimpleNamespace(ollama=11434))
    return module.llm_infra_vars


def _roles(**by_role: str) -> list:
    return [types.SimpleNamespace(role_name=role.replace("_", "-"), node_id=node) for role, node in by_role.items()]


@pytest.mark.parametrize("role", ["autobot_llm_cpu", "autobot_llm_gpu"])
def test_an_llm_on_another_node_is_named(role: str) -> None:
    got = _llm_infra_vars()(_roles(backend="b", **{role: "l"}), {"b": "fleet-backend", "l": _LLM_IP})
    assert got == {"llm_host": _LLM_IP, "llm_port": 11434}


def test_a_shared_node_stays_on_loopback() -> None:
    got = _llm_infra_vars()(_roles(backend="b", autobot_llm_cpu="b"), {"b": "fleet-backend"})
    assert got["llm_host"] == "127.0.0.1"


def test_the_gpu_node_wins_and_no_llm_role_sets_nothing() -> None:
    ips = {"b": "fleet-backend", "c": "cpu-node", "g": "gpu-node"}
    assert _llm_infra_vars()(_roles(autobot_llm_cpu="c", autobot_llm_gpu="g"), ips)["llm_host"] == "gpu-node"
    assert _llm_infra_vars()(_roles(backend="b"), ips) == {}


def _render(expression: str, **variables) -> str:
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - an env file's value, not HTML
    return env.from_string(expression).render(**variables)


@pytest.mark.parametrize("path", ["playbooks/vars/backend-env.yml", "roles/backend/defaults/main.yml"])
def test_the_endpoint_follows_the_llm_node_and_defaults_to_loopback(path: str) -> None:
    expression = yaml.safe_load((_ANSIBLE / path).read_text(encoding="utf-8"))["backend_llm_endpoint"]
    assert _render(expression) == "http://127.0.0.1:11434"
    assert _render(expression, llm_host=_LLM_IP, llm_port=11434) == f"http://{_LLM_IP}:11434"


def test_the_env_template_names_the_llm_node() -> None:
    template = (_ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2").read_text(encoding="utf-8")
    line = next(line for line in template.splitlines() if line.startswith("AUTOBOT_OLLAMA_HOST="))
    assert _render(line, llm_host=_LLM_IP) == f"AUTOBOT_OLLAMA_HOST={_LLM_IP}"
    assert _render(line) == "AUTOBOT_OLLAMA_HOST=127.0.0.1"


def test_ai_stack_follows_the_llm_node() -> None:
    defaults = yaml.safe_load((_ANSIBLE / "roles" / "ai-stack" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert _render(defaults["ollama_host"], llm_host=_LLM_IP, backend_host="b") == _LLM_IP
    assert _render(defaults["ollama_host"], backend_host="b") == "b"


def test_the_wizard_merges_the_llm_vars() -> None:
    source = (_SLM / "api" / "setup_wizard.py").read_text(encoding="utf-8")
    assert "infra_vars.update(llm_infra_vars(node_roles, node_id_to_ip))" in source
