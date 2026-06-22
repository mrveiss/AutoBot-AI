# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pipeline Configuration - Default pipeline configurations.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import copy
import re
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

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
        {"task": "add_context", "params": {}},  # Issue #1498: Contextual Retrieval
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


# Issue #3243: Audio/video/YouTube ingestion pipeline.
# Prepends a transcription step before the standard ECL stages so that the
# Whisper transcript is chunked and cognified identically to text documents.
AUDIO_KNOWLEDGE_PIPELINE = {
    "name": "audio_knowledge_enrichment",
    "batch_size": 5,
    "extract": [
        # transcribe_audio runs first; its output feeds subsequent extract tasks
        {"task": "transcribe_audio", "params": {"whisper_model": "base"}},
        {"task": "classify_document", "params": {}},
        {"task": "chunk_text", "params": {"max_tokens": 512, "overlap": 50}},
        {"task": "extract_metadata", "params": {}},
    ],
    "cognify": [
        {"task": "extract_entities", "params": {}},
        {"task": "extract_relationships", "params": {}},
        {"task": "summarize", "params": {"levels": ["sentence", "paragraph"]}},
        {"task": "add_context", "params": {}},
    ],
    "load": [
        {"task": "chromadb", "params": {}},
    ],
}


# Issue #9018 Phase 2: KAG (Knowledge-Augmented Generation) ingestion profile.
# Reuses the default ECL entity/relationship cognifiers and adds the
# mesh_seeder + redis_graph loaders so entities/relations are persisted into
# AutoBotMemoryGraph for graph-traversal retrieval. NOT always-on: selected via
# get_kag_pipeline_config() when a collection is flagged KAG (enable_kag).
KAG_KNOWLEDGE_PIPELINE = {
    "name": "kag_knowledge_enrichment",
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
        {"task": "add_context", "params": {}},
    ],
    "load": [
        {"task": "chromadb", "params": {}},
        # Graph persistence for KAG: build entity/relationship edges into the graph.
        {"task": "mesh_seeder", "params": {}},
        {"task": "redis_graph", "params": {}},
    ],
}


def get_default_config() -> Dict[str, Any]:
    """
    Get the default knowledge enrichment pipeline configuration.

    Returns:
        Default pipeline configuration dict (deep copy)
    """
    return copy.deepcopy(DEFAULT_KNOWLEDGE_PIPELINE)


def get_audio_pipeline_config() -> Dict[str, Any]:
    """Return the audio/video pipeline configuration (Issue #3243).

    Returns:
        Audio pipeline configuration dict (deep copy)
    """
    return copy.deepcopy(AUDIO_KNOWLEDGE_PIPELINE)


def get_kag_pipeline_config() -> Dict[str, Any]:
    """Return the KAG ingestion pipeline configuration (Issue #9018 Phase 2).

    Configurable profile (not always-on): callers select this for collections
    flagged KAG so ECL entity/relationship extraction + mesh_seeder seed the
    knowledge graph. Reuses existing cognifiers/loaders — no reimplementation.

    Returns:
        KAG pipeline configuration dict (deep copy)
    """
    return copy.deepcopy(KAG_KNOWLEDGE_PIPELINE)


def select_pipeline_config(kag_enabled: bool = False) -> Dict[str, Any]:
    """Return the ingestion pipeline config for a collection.

    Issue #9018 Phase 2: a configurable profile flag, not forced on. When
    kag_enabled is True the KAG profile (graph-seeding) is used; otherwise the
    standard default profile is returned unchanged (inert default).

    Args:
        kag_enabled: Whether the target collection is flagged for KAG.

    Returns:
        Pipeline configuration dict (deep copy).
    """
    return get_kag_pipeline_config() if kag_enabled else get_default_config()
