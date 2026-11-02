# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20082: a failed model download retries, and its failure says what failed and how much room was left."""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "llm"


def _pull_block() -> dict:
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    return next(t for t in tasks if any("ollama pull" in str(step) for step in t.get("block") or []))


def _retries(task: dict) -> bool:
    return bool(task.get("until") and task.get("retries"))


def test_the_pull_retries_with_values_the_role_defines() -> None:
    pull = next(step for step in _pull_block()["block"] if "ollama pull" in str(step))
    assert _retries(pull) and pull["failed_when"] == "_model_pull.rc != 0"
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["llm_pull_retries"] > 0 and defaults["llm_pull_retry_delay"] > 0


def test_the_failure_names_the_model_and_the_free_space_and_still_fails() -> None:
    rescue = _pull_block()["rescue"]
    assert "df -h" in str(rescue[0]) and rescue[0]["failed_when"] is False
    message = rescue[-1]["ansible.builtin.fail"]["msg"]
    assert "attribute='item'" in message and "_llm_models_disk" in message


def test_contrast_a_pull_without_retries_is_seen() -> None:
    assert not _retries({"ansible.builtin.command": {"cmd": "ollama pull x"}})
