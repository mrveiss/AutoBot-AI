# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Synthesis schema loader for DocIndexerService.

Loads and validates the YAML-driven synthesis configuration that maps
document collections to synthesis targets and prompt templates.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {"name", "paths", "synthesis_target", "prompt_template"}
_ALLOWED_KEYS = _REQUIRED_KEYS


@dataclass
class CollectionConfig:
    """Configuration for one synthesis collection."""

    name: str
    paths: List[str]
    synthesis_target: str
    prompt_template: str


@dataclass
class SynthesisSchema:
    """Top-level synthesis schema loaded from YAML."""

    collections: List[CollectionConfig] = field(default_factory=list)


def _parse_collection(raw: dict, index: int) -> CollectionConfig:
    """Parse and validate a single collection entry. Raises ValueError on unknown keys."""
    unknown = set(raw.keys()) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"Collection[{index}] has unknown keys: {sorted(unknown)}. "
            f"Allowed keys are: {sorted(_ALLOWED_KEYS)}"
        )
    missing = _REQUIRED_KEYS - set(raw.keys())
    if missing:
        raise ValueError(
            f"Collection[{index}] is missing required keys: {sorted(missing)}"
        )
    return CollectionConfig(
        name=str(raw["name"]),
        paths=[str(p) for p in raw["paths"]],
        synthesis_target=str(raw["synthesis_target"]),
        prompt_template=str(raw["prompt_template"]),
    )


def load_synthesis_schema(path: Optional[Path] = None) -> SynthesisSchema:
    """Load and validate synthesis_schema.yaml.

    Args:
        path: Explicit path to the YAML file. Defaults to the bundled
              resources/knowledge/synthesis_schema.yaml relative to this file.

    Returns:
        SynthesisSchema with validated collection configs, or an empty schema
        if the file is absent (a warning is emitted by the caller).

    Raises:
        ValueError: If the YAML contains unknown or missing keys.
    """
    if path is None:
        path = (
            Path(__file__).parent.parent.parent
            / "resources"
            / "knowledge"
            / "synthesis_schema.yaml"
        )

    if not path.exists():
        logger.debug("Synthesis schema not found at %s — returning empty schema", path)
        return SynthesisSchema()

    with open(path, encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh)

    if not isinstance(raw_data, dict) or "collections" not in raw_data:
        raise ValueError(
            f"synthesis_schema.yaml must have a top-level 'collections' key; got: "
            f"{list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data).__name__}"
        )

    collections = [
        _parse_collection(entry, i)
        for i, entry in enumerate(raw_data["collections"])
    ]
    return SynthesisSchema(collections=collections)
