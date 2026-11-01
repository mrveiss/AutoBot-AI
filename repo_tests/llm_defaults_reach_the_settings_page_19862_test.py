# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A fresh install's LLM settings show the role's models, and nothing pulls an empty list (#19862).

With no saved setting, the page sent empty lists that overrode the role's 7 defaults, so Apply pulled
nothing and reported "All 0 models present".
"""

from __future__ import annotations

import ast
import importlib.util
import json

import yaml
from repo_tests._paths import repo_root

_SLM = repo_root() / "autobot-slm-backend"
_ROLE = _SLM / "ansible" / "roles" / "llm"


def _models():
    spec = importlib.util.spec_from_file_location("_llm_models_19862", _SLM / "services" / "llm_default_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.default_llm_models


def _ollama_settings(rows: dict) -> dict:
    """The shipped settings reader, with its helper; the suite's stubs make the API module unimportable."""
    tree = ast.parse((_SLM / "api" / "llm_config.py").read_text(encoding="utf-8"))
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_json_list", "_ollama_settings")]
    assert len(wanted) == 2
    namespace = {"json": json, "Dict": dict, "List": list, "default_llm_models": _models()}
    exec(compile(ast.Module(wanted, []), "llm_config", "exec"), namespace)  # noqa: S102 - the repo's own source
    return namespace["_ollama_settings"](rows)


def _role_defaults() -> dict:
    return yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))


def test_the_defaults_are_the_role_s_own() -> None:
    gpu, cpu = _models()()
    assert gpu == _role_defaults()["llm_gpu_models"] and cpu == _role_defaults()["llm_cpu_models"]
    assert gpu and cpu


def test_no_saved_setting_shows_the_role_s_lists() -> None:
    settings = _ollama_settings({})
    assert settings["gpu_models"] == _role_defaults()["llm_gpu_models"]
    assert settings["cpu_models"] == _role_defaults()["llm_cpu_models"]


def test_an_empty_saved_list_falls_back_and_a_real_choice_is_kept() -> None:
    settings = _ollama_settings({"llm_gpu_models": "[]", "llm_cpu_models": '["mine:latest"]'})
    assert settings["gpu_models"] == _role_defaults()["llm_gpu_models"]
    assert settings["cpu_models"] == ["mine:latest"]


def test_the_role_refuses_an_empty_pull_list_before_pulling() -> None:
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    names = [str(task.get("name", "")) for task in tasks]
    guard = names.index("Models | There is something to pull")
    assert guard < names.index("Models | Pull models, retrying a failed download")
    assert tasks[guard]["ansible.builtin.assert"]["that"] == ["_llm_models_to_pull | length > 0"]
