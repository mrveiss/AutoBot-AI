# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Extractor for config file content from read_file tool output (MVA-1433).

Triggered when the file path ends in .yml/.yaml/.toml/.json.
Parses top-level scalar key-value pairs and produces:
  config:{path}/{key}  →  value @ confidence 0.9
"""

from __future__ import annotations

import json
import re
from typing import Any

_CONFIG_EXTENSIONS = {".yml", ".yaml", ".toml", ".json"}


def _is_config_path(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in _CONFIG_EXTENSIONS)


def _parse_yaml(content: str) -> dict:
    try:
        import yaml  # type: ignore[import-untyped]
        result = yaml.safe_load(content)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _parse_toml(content: str) -> dict:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        result = tomllib.loads(content)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _parse_json(content: str) -> dict:
    try:
        result = json.loads(content)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _parse_config(path: str, content: str) -> dict:
    lower = path.lower()
    if lower.endswith(".toml"):
        return _parse_toml(content)
    if lower.endswith(".json"):
        return _parse_json(content)
    # .yml / .yaml
    return _parse_yaml(content)


class ConfigFileExtractor:
    """Extract top-level scalar key-value assertions from config file content."""

    CONFIDENCE = 0.9

    def extract(self, tool_output: Any) -> list[tuple[str, Any, float]]:
        """Return (key, value, confidence) triples for top-level scalars.

        Only fires when the file path ends in a recognised config extension.
        Malformed or empty files silently return [].
        """
        if not isinstance(tool_output, dict):
            return []

        path = tool_output.get("path") or tool_output.get("file_path") or tool_output.get("filename")
        if not path or not _is_config_path(str(path)):
            return []

        if tool_output.get("error"):
            return []

        content = tool_output.get("content") or tool_output.get("text") or tool_output.get("data")
        if not isinstance(content, str) or not content.strip():
            return []

        parsed = _parse_config(str(path), content)
        if not parsed:
            return []

        results: list[tuple[str, Any, float]] = []
        for key, value in parsed.items():
            if isinstance(value, (str, int, float, bool)):
                assertion_key = f"config:{path}/{key}"
                results.append((assertion_key, value, self.CONFIDENCE))

        return results
