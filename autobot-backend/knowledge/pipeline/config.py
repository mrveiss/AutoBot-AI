# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pipeline Configuration - Default pipeline configurations.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import copy
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Default knowledge enrichment pipeline configuration
DEFAULT_KNOWLEDGE_PIPELINE = {
    "name": "knowledge_enrichment",
    "batch_size": 10,
    "extract": [
        {"task": "classify_document", "params": {}},
        {"task": "chunk_text", "params": {"max_tokens": 512, "overlap": 50}},
        {"task": "extract_metadata", "params": {}},
    ],
    "cognify": [
        {"task": "extract_entities", "params": {}},
        {"task": "extract_relationships", "params": {}},
        {"task": "summarize", "params": {"levels": ["sentence", "paragraph"]}},
    ],
    "load": [
        {"task": "chromadb", "params": {}},
    ],
}


def load_pipeline_config(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load and validate pipeline configuration.

    Args:
        config_dict: Pipeline configuration dictionary

    Returns:
        Validated configuration dict

    Raises:
        ValueError: If configuration is invalid
    """
    required_fields = ["name", "extract"]
    for field in required_fields:
        if field not in config_dict:
            raise ValueError(f"Missing required config field: {field}")

    _validate_stage_config(config_dict.get("extract", []), "extract")
    _validate_stage_config(config_dict.get("cognify", []), "cognify")
    _validate_stage_config(config_dict.get("load", []), "load")

    logger.info("Loaded pipeline config: %s", config_dict["name"])
    return config_dict


def _validate_stage_config(stage_config: list, stage_name: str) -> None:
    """
    Validate stage configuration. Helper for load_pipeline_config (#665).

    Args:
        stage_config: List of task configurations
        stage_name: Stage name for error messages

    Raises:
        ValueError: If stage configuration is invalid
    """
    if not isinstance(stage_config, list):
        raise ValueError(f"{stage_name} config must be a list")

    _safe_name = re.compile(r"^[a-zA-Z0-9_-]+$")
    for idx, task_config in enumerate(stage_config):
        if not isinstance(task_config, dict):
            raise ValueError(f"{stage_name}[{idx}] must be a dict")
        if "task" not in task_config:
            raise ValueError(f"{stage_name}[{idx}] missing 'task' field")
        task_name = task_config["task"]
        if not isinstance(task_name, str) or not _safe_name.match(task_name):
            raise ValueError(f"{stage_name}[{idx}] invalid task name")


def get_default_config() -> Dict[str, Any]:
    """
    Get the default knowledge enrichment pipeline configuration.

    Returns:
        Default pipeline configuration dict (deep copy)
    """
    return copy.deepcopy(DEFAULT_KNOWLEDGE_PIPELINE)
