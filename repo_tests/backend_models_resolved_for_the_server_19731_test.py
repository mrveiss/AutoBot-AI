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
    return _run_reply(json.dumps({"models": [{"name": m} for m in held]}), roles)


def _run_reply(reply, roles: dict | None = None) -> dict:
    payload = {"tags_reply": reply, "gpu_models": _GPU, "roles": roles or _ROLES, "fallback": "phi3:mini"}
    done = subprocess.run(
        [sys.executable, str(repo_root() / _SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "BACKEND_MODEL_INPUT": json.dumps(payload)},
    )
    out = json.loads(done.stdout)
    out.pop("moved")
    return out


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


@pytest.mark.parametrize(
    "reply",
    ["<html>not json</html>", "", "{}", '{"models": null}', '{"models": [{"size": 1}]}', "[]", '"text"'],
    ids=["html", "empty", "no-key", "null", "no-name", "list", "string"],
)
def test_a_reply_it_cannot_read_changes_nothing(reply: str) -> None:
    assert _run_reply(reply) == {"remap": {}, "missing": {}}


def test_a_reply_ansible_already_parsed_into_a_mapping_is_read() -> None:
    assert _run_reply({"models": [{"name": m} for m in _CPU]}) == {"remap": _REMAPPED, "missing": {}}


def test_a_move_names_the_role_and_both_models() -> None:
    payload = {
        "tags_reply": json.dumps({"models": [{"name": m} for m in _CPU]}),
        "gpu_models": _GPU,
        "roles": {"backend_instruction_model": "mistral:7b-instruct", "backend_system_model": ""},
        "fallback": "phi3:mini",
    }
    done = subprocess.run(
        [sys.executable, str(repo_root() / _SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "BACKEND_MODEL_INPUT": json.dumps(payload)},
    )
    assert json.loads(done.stdout)["moved"] == [
        ["backend_instruction_model", "mistral:7b-instruct", "phi3:mini"],
        ["backend_system_model", "(template default)", "phi3:mini"],
    ]


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
    resolve = text.index("resolve_models.yml")
    assert resolve < text.index("src: ", resolve), "the resolve must come before the render"
    assert text.index("read_deployed_embedding_model.yml") < resolve, "and after the deployed embedding read (#15502)"


def test_the_check_asks_the_server_agents_call() -> None:
    text = (repo_root() / _ANS / "roles/backend/tasks/resolve_models.yml").read_text(encoding="utf-8")
    assert "backend_llm_endpoint" in text


def test_the_updater_only_warns_on_a_missing_model() -> None:
    text = (repo_root() / _ANS / "playbooks/update-all-nodes.yml").read_text(encoding="utf-8")
    render = text[text.index("tasks_from: env_only") :]
    assert "backend_model_check_warn_only: true" in render[: render.index("backend_env_dest")]


@pytest.mark.parametrize("playbook", ["deploy.yml", "playbooks/provision-fleet-roles.yml"])
def test_a_play_that_pulls_after_the_backend_only_warns_at_the_backend(playbook: str) -> None:
    """A model a later LLM role would pull must not stop the deploy before that role runs."""
    docs = yaml.safe_load((repo_root() / "autobot-slm-backend/ansible" / playbook).read_text(encoding="utf-8"))
    tasks = [t for play in docs for t in (play.get("tasks") or []) if isinstance(t, dict)]
    names = [(t.get("ansible.builtin.include_role") or {}).get("name") for t in tasks]
    assert "llm" in names[names.index("backend") :]
    assert tasks[names.index("backend")]["vars"]["backend_model_check_warn_only"] is True


def test_deploy_full_stays_strict_because_it_runs_no_llm_role() -> None:
    text = (repo_root() / "autobot-slm-backend/ansible/playbooks/deploy-full.yml").read_text(encoding="utf-8")
    assert "role: llm" not in text and "name: llm" not in text and "backend_model_check_warn_only" not in text
