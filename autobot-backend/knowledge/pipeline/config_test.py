# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for pipeline configuration validation.

Issue #1075: Test coverage for config.py including SEC-3 task name validation.
"""

import pytest

from knowledge.pipeline.config import (
    DEFAULT_KNOWLEDGE_PIPELINE,
    _validate_stage_config,
    get_default_config,
    load_pipeline_config,
)


class TestLoadPipelineConfig:
    """Tests for load_pipeline_config."""

    def test_valid_config(self):
        config = {
            "name": "test",
            "extract": [{"task": "classify_document"}],
            "cognify": [],
            "load": [],
        }
        result = load_pipeline_config(config)
        assert result["name"] == "test"

    def test_missing_name(self):
        config = {"extract": [{"task": "x"}]}
        with pytest.raises(ValueError, match="Missing required.*name"):
            load_pipeline_config(config)

    def test_missing_extract(self):
        config = {"name": "test"}
        with pytest.raises(ValueError, match="Missing required.*extract"):
            load_pipeline_config(config)

    def test_default_config_is_valid(self):
        result = load_pipeline_config(DEFAULT_KNOWLEDGE_PIPELINE.copy())
        assert result["name"] == "knowledge_enrichment"


class TestValidateStageConfig:
    """Tests for _validate_stage_config."""

    def test_valid_stage(self):
        stage = [{"task": "do_stuff"}, {"task": "more_stuff"}]
        _validate_stage_config(stage, "extract")

    def test_not_a_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            _validate_stage_config("not_a_list", "extract")

    def test_item_not_dict(self):
        with pytest.raises(ValueError, match="must be a dict"):
            _validate_stage_config(["not_a_dict"], "extract")

    def test_missing_task_field(self):
        with pytest.raises(ValueError, match="missing 'task' field"):
            _validate_stage_config([{"params": {}}], "extract")

    def test_empty_stage_list(self):
        _validate_stage_config([], "extract")


class TestTaskNameValidation:
    """SEC-3: Task name whitelist validation (#1073)."""

    def test_valid_alphanumeric(self):
        _validate_stage_config([{"task": "extract_entities"}], "cognify")

    def test_valid_with_hyphen(self):
        _validate_stage_config([{"task": "chunk-text"}], "extract")

    def test_valid_with_underscore(self):
        _validate_stage_config([{"task": "load_to_db"}], "load")

    def test_invalid_path_traversal(self):
        with pytest.raises(ValueError, match="invalid task name"):
            _validate_stage_config([{"task": "../../etc/passwd"}], "extract")

    def test_invalid_spaces(self):
        with pytest.raises(ValueError, match="invalid task name"):
            _validate_stage_config([{"task": "bad task name"}], "extract")

    def test_invalid_special_chars(self):
        with pytest.raises(ValueError, match="invalid task name"):
            _validate_stage_config([{"task": "task;rm -rf /"}], "extract")

    def test_invalid_empty_string(self):
        with pytest.raises(ValueError, match="invalid task name"):
            _validate_stage_config([{"task": ""}], "extract")

    def test_non_string_task_name(self):
        with pytest.raises(ValueError, match="invalid task name"):
            _validate_stage_config([{"task": 123}], "extract")


class TestGetDefaultConfig:
    """Tests for get_default_config."""

    def test_returns_copy(self):
        config1 = get_default_config()
        config2 = get_default_config()
        assert config1 is not config2

    def test_default_has_required_fields(self):
        config = get_default_config()
        assert "name" in config
        assert "extract" in config
        assert isinstance(config["extract"], list)
        assert config["batch_size"] == 10

    def test_default_has_three_extractors(self):
        config = get_default_config()
        task_names = [t["task"] for t in config["extract"]]
        assert "classify_document" in task_names
        assert "chunk_text" in task_names
        assert "extract_metadata" in task_names


# ---------------------------------------------------------------------------
# Issue #9018 Phase 2 — KAG ingestion pipeline profile
# ---------------------------------------------------------------------------

from knowledge.pipeline.config import (
    KAG_KNOWLEDGE_PIPELINE,
    get_kag_pipeline_config,
)
from knowledge.pipeline.config import load_pipeline_config as _load_pipeline_config  # noqa: E402
from knowledge.pipeline.config import (
    select_pipeline_config,
)


class TestKAGPipelineProfile:
    """Tests for the configurable KAG ingestion profile (#9018 Phase 2)."""

    def test_kag_config_validates(self):
        """KAG profile passes pipeline config validation."""
        assert _load_pipeline_config(get_kag_pipeline_config())["name"] == "kag_knowledge_enrichment"

    def test_kag_seeds_graph_loaders(self):
        """KAG profile adds mesh_seeder + redis_graph loaders alongside chromadb."""
        loaders = {t["task"] for t in get_kag_pipeline_config()["load"]}
        assert {"chromadb", "mesh_seeder", "redis_graph"} <= loaders

    def test_kag_reuses_entity_relationship_cognifiers(self):
        """KAG profile reuses existing ECL entity/relationship cognifiers."""
        cognify = {t["task"] for t in get_kag_pipeline_config()["cognify"]}
        assert {"extract_entities", "extract_relationships"} <= cognify

    def test_get_kag_config_returns_copy(self):
        """Each call returns an independent deep copy."""
        a = get_kag_pipeline_config()
        a["load"].clear()
        assert KAG_KNOWLEDGE_PIPELINE["load"], "module-level template must not mutate"

    def test_select_default_when_kag_disabled(self):
        """Inert default: kag_enabled=False → standard pipeline, no graph loaders."""
        cfg = select_pipeline_config(kag_enabled=False)
        loaders = {t["task"] for t in cfg["load"]}
        assert cfg["name"] == "knowledge_enrichment"
        assert "mesh_seeder" not in loaders

    def test_select_kag_when_enabled(self):
        """kag_enabled=True → KAG profile selected."""
        assert select_pipeline_config(kag_enabled=True)["name"] == "kag_knowledge_enrichment"
