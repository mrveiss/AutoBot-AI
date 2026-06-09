# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Manifest Parser (Issue #5063)

Parses and validates SKILL.md YAML front-matter for the open skill-manifest
standard.  The front-matter block is delimited by ``---`` lines at the very
start of the file.

Required fields : name, version, description, entrypoint
Optional fields : category, capabilities, dependencies, trust_level_requested,
                  tags, author, license, homepage
"""

import re
import warnings
from typing import Any

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_REQUIRED_FIELDS = ("name", "version", "description", "entrypoint")
_OPTIONAL_FIELDS = (
    "category",
    "capabilities",
    "dependencies",
    "trust_level_requested",
    "tags",
    "author",
    "license",
    "homepage",
    "kind",
)
_VALID_TRUST_LEVELS = {"trusted", "monitored", "sandboxed", "restricted"}
_LIST_FIELDS = ("capabilities", "dependencies", "tags")

_FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)


def parse_manifest(text: str) -> dict[str, Any]:
    """Parse YAML front-matter from a SKILL.md string.

    Args:
        text: Full SKILL.md content with ``---`` front-matter block.

    Returns:
        Parsed manifest dict.

    Raises:
        ValueError: If front-matter is missing, unparseable, or fails validation.
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md must start with a YAML front-matter block delimited by '---' lines")

    raw_yaml = match.group(1)
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in SKILL.md front-matter: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("SKILL.md front-matter must be a YAML mapping (key: value pairs)")

    errors = validate_manifest(data)
    if errors:
        raise ValueError("Manifest validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    if "kind" not in data:
        warnings.warn(
            f"Skill manifest '{data.get('name', '<unknown>')}' does not declare 'kind'; "
            "defaulting to 'skill'. Add kind: skill to silence this warning.",
            DeprecationWarning,
            stacklevel=2,
        )
        data["kind"] = "skill"

    return data


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate a parsed manifest dict and return a list of error strings.

    An empty list means the manifest is valid.

    Args:
        manifest: Dict produced by :func:`parse_manifest` or ``yaml.safe_load``.

    Returns:
        List of human-readable error strings; empty when valid.
    """
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        value = manifest.get(field)
        if not value:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(value, str):
            errors.append(f"Field '{field}' must be a string, got {type(value).__name__}")

    for field in _LIST_FIELDS:
        value = manifest.get(field)
        if value is not None and not isinstance(value, list):
            errors.append(f"Optional field '{field}' must be a list when present")
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    errors.append(f"All items in '{field}' must be strings; got {type(item).__name__}")

    trust = manifest.get("trust_level_requested")
    if trust is not None:
        if not isinstance(trust, str) or trust not in _VALID_TRUST_LEVELS:
            errors.append(f"'trust_level_requested' must be one of {sorted(_VALID_TRUST_LEVELS)}")

    known = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
    for key in manifest:
        if key not in known:
            errors.append(f"Unknown field: '{key}'")

    return errors
