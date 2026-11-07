# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-graph and ask-human settings, split out of ``ssot_config.LLMConfig`` (#21024, #20846).

``ssot_config.py`` is over the file-size ceiling and may not grow, so these live here and
``LLMConfig`` inherits them: ``config.llm.<name>`` is the single definition. The chat graph
(``chat_workflow/graph.py``) is the canonical loop; ``agent_loop/types.py`` reads the
ask-human defaults from here instead of carrying its own literals.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root


class ChatGraphSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Chat-graph planner node (#21023): off by default, no behaviour change.
    chat_planner_enabled: bool = Field(default=False, alias="AUTOBOT_CHAT_PLANNER_ENABLED")
    # Chat-graph stall escalation (#21022): "stop" halts the turn, "ask" asks the human.
    chat_stall_escalation: Literal["stop", "ask"] = Field(default="stop", alias="AUTOBOT_CHAT_STALL_ESCALATION")
    # Ask-the-human defaults (#10553): seconds to wait, then the escalation policy.
    ask_human_timeout_seconds: int = Field(default=300, alias="AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS")
    ask_human_escalation_policy: Literal["abandon", "default", "re_ask"] = Field(
        default="abandon", alias="AUTOBOT_ASK_HUMAN_ESCALATION_POLICY"
    )
