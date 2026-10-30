# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A backend whose LLM role is on another node calls that node, and a shared node stays on loopback (#19861).

The wizard wrote host vars for 7 roles and neither LLM role, so every model call went to the backend's
own loopback and chat failed on first run. These run the shipped module and render the shipped template.
"""

from __future__ import annotations

import ast
import importlib.util
import types

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_SLM = repo_root() / "autobot-slm-backend"
_ANSIBLE = _SLM / "ansible"
_LLM = "fleet-llm"
_IPS = {"b": "fleet-backend", "a": "fleet-ai", "l": _LLM}


def _placement():
    """The shipped module; loaded by path, as the suite's stubs may replace the services package."""
    spec = importlib.util.spec_from_file_location("_llm_placement_19861", _SLM / "services" / "llm_placement.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.config = types.SimpleNamespace(port=types.SimpleNamespace(ollama=11434))
    return module


def _roles(**by_role: str) -> list:
    return [types.SimpleNamespace(role_name=role.replace("_", "-"), node_id=node) for role, node in by_role.items()]


def _build_infra_vars(node_roles: list, ips: dict, local_ips=None) -> dict:
    """The wizard's own function, with its neighbours; the suite cannot import the wizard module."""
    tree = ast.parse((_SLM / "api" / "setup_wizard.py").read_text(encoding="utf-8"))
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_build_infra_vars")
    namespace = {"_ROLE_INFRA_VARS": {"backend": ("backend_host", 8001)}, "llm_infra_vars": _placement().llm_infra_vars}
    exec(compile(ast.Module([func], []), "setup_wizard", "exec"), namespace)  # noqa: S102 - the repo's own source
    return namespace["_build_infra_vars"](node_roles, ips, local_ips)


@pytest.mark.parametrize("role", ["autobot_llm_cpu", "autobot_llm_gpu"])
def test_an_llm_on_another_node_is_named_for_each_client(role: str) -> None:
    got = _build_infra_vars(_roles(backend="b", ai_stack="a", **{role: "l"}), _IPS)
    assert got["backend_ollama_host"] == _LLM and got["ai_stack_ollama_host"] == _LLM
    assert got["backend_ollama_port"] == 11434 and got["ai_stack_ollama_port"] == 11434


def test_a_client_sharing_the_node_uses_loopback_and_one_elsewhere_does_not() -> None:
    got = _build_infra_vars(_roles(backend="l", ai_stack="a", autobot_llm_cpu="l"), _IPS)
    assert got["backend_ollama_host"] == "127.0.0.1"
    assert got["ai_stack_ollama_host"] == _LLM, "an ai-stack elsewhere got the backend's loopback"


def test_the_llm_role_s_own_listen_vars_are_not_written() -> None:
    """They are Ollama's listen address, and an inventory var would outrank the role's default."""
    got = _build_infra_vars(_roles(backend="b", autobot_llm_cpu="l"), _IPS)
    assert "llm_host" not in got and "llm_port" not in got


def test_a_second_run_gives_the_same_vars() -> None:
    roles = _roles(backend="b", ai_stack="a", autobot_llm_gpu="l", autobot_llm_cpu="b")
    assert _build_infra_vars(roles, _IPS) == _build_infra_vars(roles, _IPS)
    assert _build_infra_vars(roles, _IPS)["backend_ollama_host"] == _LLM, "the GPU node did not win"


def test_no_llm_role_sets_nothing_and_an_unknown_address_warns(caplog) -> None:
    placement = _placement()
    assert placement.llm_infra_vars(_roles(backend="b"), _IPS) == {}
    warned = []
    placement.logger = types.SimpleNamespace(warning=lambda msg, *a: warned.append(msg % a))
    assert placement.llm_infra_vars(_roles(autobot_llm_cpu="gone"), _IPS) == {}
    assert warned and "gone" in warned[0]


def _full_backend_env(**variables) -> str:
    """The whole shipped template, with the shipped endpoint default; other vars render empty."""
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)  # noqa: S701 - an env file
    env.filters.update({"bool": bool, "regex_replace": lambda v, *_a, **_k: v, "to_json": str, "b64encode": str})
    source = (_ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2").read_text(encoding="utf-8")
    defaults = yaml.safe_load((_ANSIBLE / "roles" / "backend" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    endpoint = env.from_string(defaults["backend_llm_endpoint"]).render(**variables)
    return env.from_string(source).render(backend_llm_endpoint=endpoint, **variables)


def _line(rendered: str, name: str) -> str:
    return next(line for line in rendered.splitlines() if line.startswith(f"{name}="))


def test_the_rendered_env_names_the_llm_node_on_a_split_install() -> None:
    rendered = _full_backend_env(backend_ollama_host=_LLM, backend_ollama_port=11434)
    assert _line(rendered, "AUTOBOT_LLM_ENDPOINT") == f"AUTOBOT_LLM_ENDPOINT=http://{_LLM}:11434"
    assert _line(rendered, "AUTOBOT_OLLAMA_HOST") == f"AUTOBOT_OLLAMA_HOST={_LLM}"


def test_the_rendered_env_stays_on_loopback_on_a_single_node() -> None:
    rendered = _full_backend_env()
    assert _line(rendered, "AUTOBOT_LLM_ENDPOINT") == "AUTOBOT_LLM_ENDPOINT=http://127.0.0.1:11434"
    assert _line(rendered, "AUTOBOT_OLLAMA_HOST") == "AUTOBOT_OLLAMA_HOST=127.0.0.1"


def test_ai_stack_follows_its_own_vars() -> None:
    defaults = yaml.safe_load((_ANSIBLE / "roles" / "ai-stack" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - an env file's value
    host, port = env.from_string(defaults["ollama_host"]), env.from_string(defaults["ollama_port"])
    assert host.render(ai_stack_ollama_host=_LLM, backend_host="b") == _LLM
    assert host.render(backend_host="b") == "b"
    assert port.render(ai_stack_ollama_port=11500) == "11500" and port.render() == "11434"
