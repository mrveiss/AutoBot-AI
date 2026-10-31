# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The planner model is the source-of-truth planning tier, not a GUI or settings.json value (#15502)."""

from unittest.mock import MagicMock

from autobot_shared.ssot_config import config
from orchestration.orchestrator_config import OrchestratorConfig


def _manager(llm_config: dict) -> MagicMock:
    manager = MagicMock()
    manager.get_llm_config.return_value = llm_config
    manager.get.side_effect = lambda _key, default=None: default
    return manager


def test_the_planner_model_is_the_ssot_planning_tier() -> None:
    assert OrchestratorConfig(_manager({})).orchestrator_llm_model == config.llm.planning_model


def test_a_gui_selected_or_settings_model_does_not_drive_planning() -> None:
    llm_config = {"orchestrator_llm": "settings-json-model:1b", "ollama": {"selected_model": "gui-selected:7b"}}
    planner = OrchestratorConfig(_manager(llm_config)).orchestrator_llm_model
    assert planner == config.llm.planning_model
    assert planner not in {"settings-json-model:1b", "gui-selected:7b"}


def test_the_task_model_still_follows_the_configured_task_llm() -> None:
    llm_config = {"task_llm": "ollama_x", "ollama": {"selected_model": "gui-selected:7b"}}
    assert OrchestratorConfig(_manager(llm_config)).task_llm_model == "ollama_x"
