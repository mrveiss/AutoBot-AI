# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ToolOutputFilter — declarative pipeline for cleaning command stdout before it
reaches the LLM.  Replaces naive byte-slice truncation at scattered sites.

Usage::

    from services.tool_output_filter import ToolOutputFilter
    _filter = ToolOutputFilter()
    clean = _filter.filter("pytest tests/", raw_output)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "config", "tool_output_filters.yaml"
)


class ToolOutputFilter:
    """Apply a rule-based pipeline to tool command output."""

    def __init__(self, config_path: str | None = None) -> None:
        path = config_path or _DEFAULT_CONFIG
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            self._rules: list[dict[str, Any]] = list(cfg.get("filters", {}).values())
        except FileNotFoundError:
            logger.warning("tool_output_filter: config not found at %s", path)
            self._rules = []
        except Exception:
            logger.exception("tool_output_filter: failed to load config from %s", path)
            self._rules = []

    def filter(self, command: str, output: str) -> str:
        """Return filtered *output* for *command*.  Passthrough if no rule matches."""
        rule = self._match_rule(command)
        if rule is None:
            return output
        return self._apply(rule, output)

    def _match_rule(self, command: str) -> dict[str, Any] | None:
        cmd = command.strip()
        for rule in self._rules:
            pattern = rule.get("match_command", "")
            if pattern and re.search(pattern, cmd):
                return rule
        return None

    def _apply(self, rule: dict[str, Any], text: str) -> str:
        if rule.get("strip_ansi"):
            text = _strip_ansi(text)

        if "match_output" in rule:
            for entry in rule["match_output"]:
                if re.search(entry["pattern"], text, re.MULTILINE):
                    return entry["message"]

        if "strip_lines_matching" in rule:
            patterns = [re.compile(p) for p in rule["strip_lines_matching"]]
            text = "\n".join(
                line for line in text.splitlines()
                if not any(p.search(line) for p in patterns)
            )

        if "keep_lines_matching" in rule:
            patterns = [re.compile(p) for p in rule["keep_lines_matching"]]
            text = "\n".join(
                line for line in text.splitlines()
                if any(p.search(line) for p in patterns)
            )

        if rule.get("dedup_consecutive"):
            text = _dedup_consecutive(text)

        max_lines = rule.get("max_lines")
        if max_lines and max_lines > 0:
            lines = text.splitlines()
            if len(lines) > max_lines:
                text = "\n".join(lines[-max_lines:])

        if not text.strip():
            return rule.get("on_empty", "")

        return text


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _dedup_consecutive(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    count = 1
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and lines[i + 1] == line:
            count += 1
        else:
            result.append(f"{line} [×{count}]" if count > 1 else line)
            count = 1
    return "\n".join(result)
