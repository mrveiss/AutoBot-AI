# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Config-protection guard for the agent loop (GH#11148).

Blocks agent write/edit/delete/move tools that target a linter or formatter
config file, so the agent fixes the code to satisfy a quality gate instead of
silently weakening the gate (e.g. adding an ``ignore`` rule to ``.eslintrc`` or
``ruff.toml``). Mixed-purpose manifests (``pyproject.toml``, ``setup.cfg``) are
intentionally NOT protected here — they carry legitimate non-lint content
(dependencies, packaging) and blocking them would over-block.

Override with ``AUTOBOT_ALLOW_CONFIG_EDITS=1`` when an intentional config change
is required.
"""

import os

# Write-side tools whose target path is guarded. Read/list tools are ignored.
_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "multi_edit",
        "apply_patch",
        "create_file",
        "delete_file",
        "move_file",
        "copy_file",
    }
)

# Arg keys under which a write tool carries its target path (see
# tools/parallel/analyzer.py RESOURCE_EXTRACTORS).
_PATH_KEYS: tuple[str, ...] = ("file_path", "path", "destination", "target_file")

# Dedicated linter/formatter config basenames (exact, case-insensitive).
_PROTECTED_BASENAMES: frozenset[str] = frozenset(
    {
        ".editorconfig",
        ".pre-commit-config.yaml",
        ".flake8",
        "mypy.ini",
        ".mypy.ini",
        "ruff.toml",
        ".ruff.toml",
        ".isort.cfg",
        ".pylintrc",
        "tox.ini",
        "eslint.config.js",
        "eslint.config.cjs",
        "eslint.config.mjs",
        "prettier.config.js",
        "prettier.config.cjs",
        "prettier.config.mjs",
        "commitlint.config.js",
        "commitlint.config.cjs",
        "commitlint.config.mjs",
        "stylelint.config.js",
        "biome.json",
        "biome.jsonc",
    }
)

# Basename prefixes covering the many dotfile variants (``.eslintrc.json``,
# ``.prettierrc.yaml``, ``.markdownlint.json`` …).
_PROTECTED_PREFIXES: tuple[str, ...] = (
    ".eslintrc",
    ".prettierrc",
    ".stylelintrc",
    ".markdownlint",
)


def is_protected_config(path: str | None) -> str | None:
    """Return the matched config basename if *path* is a protected config, else None."""
    if not path:
        return None
    base = os.path.basename(str(path).strip().rstrip("/\\"))
    lower = base.lower()
    if lower in _PROTECTED_BASENAMES:
        return base
    if any(lower.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
        return base
    return None


def config_edits_allowed() -> bool:
    """True when ``AUTOBOT_ALLOW_CONFIG_EDITS`` opts out of the guard."""
    return os.environ.get("AUTOBOT_ALLOW_CONFIG_EDITS", "").strip().lower() in {"1", "true", "yes"}


def protected_config_write(tool: dict) -> str | None:
    """Return the protected config basename a write-tool call targets, else None."""
    name = str(tool.get("tool_name", "")).lower()
    if name not in _WRITE_TOOLS:
        return None
    args = tool.get("args") or tool.get("arguments") or tool.get("parameters") or {}
    if not isinstance(args, dict):
        return None
    for key in _PATH_KEYS:
        matched = is_protected_config(args.get(key))
        if matched:
            return matched
    return None
