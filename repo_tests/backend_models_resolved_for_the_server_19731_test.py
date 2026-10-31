# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The backend env names models the server holds, and a missing one is named with its role (#19731)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
import yaml
from repo_tests._paths import repo_root

_ANS = "autobot-slm-backend/ansible"
_SCRIPT = f"{_ANS}/_shared/files/resolve_backend_models.py"
_GPU = ["qwen3.5:9b", "mistral:7b-instruct", "dolphin-llama3:8b"]
_CPU = ["nomic-embed-text:latest", "llama3.2:1b", "gemma2:2b", "phi3:mini"]
_ROLES = {
    "backend_llm_model": "qwen3.5:9b",
    "backend_light_model": "phi3:mini",
    "backend_instruction_model": "mistral:7b-instruct",
    "backend_system_model": "dolphin-llama3:8b",
    "backend_embedding_model": "nomic-embed-text:latest",
}
_REMAPPED = {
    "backend_llm_model": "phi3:mini",
    "backend_instruction_model": "phi3:mini",
    "backend_system_model": "phi3:mini",
}


def _run(held: list[str], roles: dict | None = None) -> dict:
    payload = {"held": held, "gpu_models": _GPU, "roles": roles or _ROLES, "fallback": "phi3:mini"}
    done = subprocess.run(
        [sys.executable, str(repo_root() / _SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "BACKEND_MODEL_INPUT": json.dumps(payload)},
    )
    return json.loads(done.stdout)


def test_a_cpu_only_server_points_gpu_roles_at_a_model_it_holds() -> None:
    assert _run(_CPU) == {"remap": _REMAPPED, "missing": {}}


def test_a_server_holding_every_model_changes_nothing() -> None:
    assert _run(_CPU + _GPU) == {"remap": {}, "missing": {}}


def test_latest_tags_compare_equal() -> None:
    held = ["nomic-embed-text", "phi3:mini", "llama3.2:1b", *_GPU]
    assert _run(held) == {"remap": {}, "missing": {}}


def test_a_gpu_server_missing_one_gpu_model_reports_it_rather_than_hiding_it() -> None:
    held = [m for m in _CPU + _GPU if m != "mistral:7b-instruct"]
    assert _run(held) == {"remap": {}, "missing": {"backend_instruction_model": "mistral:7b-instruct"}}


def test_a_missing_cpu_model_is_named_with_its_role_on_a_cpu_only_server() -> None:
    held = [m for m in _CPU if m != "nomic-embed-text:latest"]
    assert _run(held) == {"remap": _REMAPPED, "missing": {"backend_embedding_model": "nomic-embed-text:latest"}}


def test_an_unset_role_is_not_reported_as_missing() -> None:
    assert _run(_CPU + _GPU, {"backend_embedding_model": ""}) == {"remap": {}, "missing": {}}


def test_an_unset_gpu_tier_role_is_remapped_on_a_cpu_only_server() -> None:
    assert _run(_CPU, {"backend_instruction_model": "", "backend_routing_model": ""}) == {
        "remap": {"backend_instruction_model": "phi3:mini"},
        "missing": {},
    }


def test_an_empty_server_proves_nothing() -> None:
    assert _run([]) == {"remap": {}, "missing": {}}


def test_no_fallback_held_means_no_remap_and_every_absent_model_named() -> None:
    held = ["llama3.2:1b"]
    out = _run(held)
    assert out["remap"] == {}
    assert out["missing"]["backend_light_model"] == "phi3:mini"
    assert out["missing"]["backend_llm_model"] == "qwen3.5:9b"


def test_the_gpu_list_here_is_the_roles_list() -> None:
    defaults = yaml.safe_load((repo_root() / _ANS / "roles/llm/defaults/main.yml").read_text(encoding="utf-8"))
    assert sorted(defaults["llm_gpu_models"]) == sorted(_GPU), "the mapping reads this list from the role"


@pytest.mark.parametrize(
    "site",
    [
        "roles/backend/tasks/main.yml",
        "roles/backend/tasks/env_only.yml",
        "playbooks/deploy-backend-env.yml",
        "roles/backend_services/tasks/main.yml",
    ],
)
def test_every_render_of_the_backend_env_resolves_first(site: str) -> None:
    text = (repo_root() / _ANS / site).read_text(encoding="utf-8")
    assert text.index("resolve_models.yml") < text.index("backend.env.j2", text.index("resolve_models.yml"))


def test_the_updater_only_warns_on_a_missing_model() -> None:
    text = (repo_root() / _ANS / "playbooks/update-all-nodes.yml").read_text(encoding="utf-8")
    render = text[text.index("tasks_from: env_only") :]
    assert "backend_model_check_warn_only: true" in render[: render.index("backend_env_dest")]
