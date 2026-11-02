# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A config.yaml model that disagrees with the tier map is warned about once, never rewritten (#15502)."""

import copy
import logging

from autobot_shared.ssot_config import config
from config.model_drift import selected_model_drift, warn_on_selected_model_drift
from config.validation import ValidationMixin

_LOGGER = "config.model_drift"


def _raw(local: str, embedding: str | None = None) -> dict:
    llm: dict = {"local": {"providers": {"ollama": {"selected_model": local, "host": "h"}}}}
    if embedding is not None:
        llm["embedding"] = {"providers": {"ollama": {"selected_model": embedding}}}
    return {"backend": {"llm": llm}}


def test_agreeing_models_warn_nothing(caplog) -> None:
    raw = _raw(config.llm.default_model, config.llm.embedding_model)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert warn_on_selected_model_drift(raw) == []
    assert caplog.records == []


def test_latest_tag_is_the_same_embedding_model() -> None:
    raw = _raw(config.llm.default_model, config.llm.embedding_model.removesuffix(":latest") + ":latest")
    assert selected_model_drift(raw) == []


def test_one_warning_names_the_key_path_the_file_value_and_the_tier_value(caplog) -> None:
    raw = _raw("phi3:mini", "stale-embed:1")
    before = copy.deepcopy(raw)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        drift = warn_on_selected_model_drift(raw)
    assert [d[0] for d in drift] == [
        "backend.llm.local.providers.ollama.selected_model",
        "backend.llm.embedding.providers.ollama.selected_model",
    ]
    assert len(caplog.records) == 1, "ONE warning, however many keys drift"
    message = caplog.records[0].getMessage()
    assert caplog.records[0].levelno == logging.WARNING
    assert "backend.llm.local.providers.ollama.selected_model" in message
    assert "'phi3:mini'" in message and repr(config.llm.default_model) in message
    assert "'stale-embed:1'" in message and repr(config.llm.embedding_model) in message
    assert raw == before, "nothing is rewritten"


def test_a_block_without_a_model_or_a_providers_parent_is_ignored() -> None:
    raw = {"backend": {"llm": {"selected_model": "x", "local": {"providers": {"ollama": {"host": "h"}}}}}}
    assert selected_model_drift(raw) == []
    assert selected_model_drift({}) == []


def test_startup_validation_runs_the_drift_check(caplog) -> None:
    class _Manager(ValidationMixin):
        _config = _raw("phi3:mini")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        _Manager().validate_startup()
    assert [r for r in caplog.records if r.name == _LOGGER and "phi3:mini" in r.getMessage()]
