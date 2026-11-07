# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""ChatGraphSettings fails fast on bad values, naming the variable (#21024)."""

import pytest
from pydantic import ValidationError

from autobot_shared.ssot_chat_graph_settings import ChatGraphSettings


def test_valid_values_load(monkeypatch):
    monkeypatch.setenv("AUTOBOT_ASK_HUMAN_ESCALATION_POLICY", "re_ask")
    assert ChatGraphSettings().ask_human_escalation_policy == "re_ask"


@pytest.mark.parametrize("var", ["AUTOBOT_ASK_HUMAN_ESCALATION_POLICY", "AUTOBOT_CHAT_STALL_ESCALATION"])
def test_typo_names_variable_and_allowed_values(monkeypatch, var):
    monkeypatch.setenv(var, "bogus")
    with pytest.raises(ValidationError) as err:
        ChatGraphSettings()
    assert var in str(err.value) and "must be one of" in str(err.value)


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_timeout_has_a_lower_bound(monkeypatch, bad):
    monkeypatch.setenv("AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS", bad)
    with pytest.raises(ValidationError):
        ChatGraphSettings()


def test_llm_config_inherits_the_one_config_dict():
    """LLMConfig carries ChatGraphSettings' (#21024)."""
    from autobot_shared.ssot_config import LLMConfig

    for key in ("env_file", "env_file_encoding", "extra"):
        assert LLMConfig.model_config[key] == ChatGraphSettings.model_config[key]
    assert LLMConfig.model_config["extra"] == "ignore"
