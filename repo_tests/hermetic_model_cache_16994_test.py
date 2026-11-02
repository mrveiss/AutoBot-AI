# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests see an empty HuggingFace cache, whatever the machine has (#16994)."""

import os
from pathlib import Path

import pytest
from repo_tests import hermetic_model_cache


def test_every_cache_variable_points_inside_the_session_root():
    root = Path(hermetic_model_cache.cache_root())
    for var in hermetic_model_cache.CACHE_ENV_VARS:
        assert Path(os.environ[var]).is_relative_to(root), var


def test_huggingface_hub_resolved_the_session_cache_at_import():
    from huggingface_hub import constants

    assert Path(constants.HF_HUB_CACHE).is_relative_to(Path(hermetic_model_cache.cache_root()))


def test_a_model_outside_the_allow_list_is_reported(tmp_path):
    (tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2").mkdir()
    (tmp_path / "models--Salesforce--blip2-opt-2.7b").mkdir()
    (tmp_path / ".locks").mkdir()
    assert hermetic_model_cache.unexpected_models(tmp_path) == ["models--Salesforce--blip2-opt-2.7b"]


def test_a_missing_cache_reports_nothing(tmp_path):
    assert hermetic_model_cache.unexpected_models(tmp_path / "absent") == []


def test_the_real_user_cache_is_not_the_one_in_use():
    user_cache = Path.home() / ".cache" / "huggingface"
    assert not Path(os.environ["HF_HOME"]).is_relative_to(user_cache)


def test_model_hubs_are_offline_so_nothing_is_downloaded():
    for var in hermetic_model_cache.OFFLINE_ENV_VARS:
        assert os.environ[var] == "1", var


def test_without_a_marker_the_hub_stays_offline():
    constants = pytest.importorskip("huggingface_hub.constants")
    assert constants.HF_HUB_OFFLINE is True


@pytest.mark.hf_model("sentence-transformers/all-MiniLM-L6-v2")
def test_an_allow_listed_model_lifts_offline_mode_for_its_test():
    constants = pytest.importorskip("huggingface_hub.constants")
    assert constants.HF_HUB_OFFLINE is False
    assert os.environ["HF_HUB_OFFLINE"] == "0"


def test_every_allowed_download_names_its_reason():
    for repo_id, reason in hermetic_model_cache.ALLOWED_DOWNLOADS.items():
        assert "/" in repo_id and reason.strip(), repo_id


def test_an_unlisted_model_fails_the_test_that_asks_for_it():
    with pytest.raises(pytest.fail.Exception, match="not in ALLOWED_DOWNLOADS"):
        hermetic_model_cache.require_allowed("Salesforce/blip2-opt-2.7b")
