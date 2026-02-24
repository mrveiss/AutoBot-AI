# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
