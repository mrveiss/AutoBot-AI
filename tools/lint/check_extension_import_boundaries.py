#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pre-commit hook: block imports that violate the extension/skill/plugin
layer boundary (#7372).

Rules enforced:
  1. Files under extensions/builtin/, skills/builtin/, or plugins/core-plugins/
     must NOT import from autobot-backend core modules.
     Allowed: autobot_shared.* (public SDK), own package, stdlib, third-party.

  2. Extensions must NOT import sibling extensions (except in __init__.py).

  3. Skills must NOT import sibling skills (except in __init__.py).

Waiver: add ``# nosemgrep: extension-no-core-internals`` (or the relevant
rule id) as an inline comment. All waivers should explain *why*.

Usage:
  python tools/lint/check_extension_import_boundaries.py [file1.py file2.py ...]
  If no files are given, reads from stdin (pre-commit passes staged files).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Packages/modules that are allowed at the extension/skill/plugin layer.
# autobot_shared is the approved public surface.
_ALLOWED_TOP_LEVEL = {
    "autobot_shared",
    # own-package imports (relative or absolute) are handled separately
}

# Forbidden core-backend packages (not exhaustive — any non-allowed import
# from the autobot-backend namespace is blocked).
_CORE_BACKEND_PACKAGES = {
    "api",
    "chat_history",
    "chat_workflow",
    "initialization",
    "integrations",
    "knowledge",
    "llm_interface_pkg",
    "llm_providers",
    "models",
    "permissions",
    "prompt_manager",
    "secure_command_executor",
    "skills",  # top-level skills pkg from another extension is a violation
    "extensions",  # sibling cross-import — covered by dedicated rules below
    "services",
    "tasks",
    "utils",
    "workers",
}


def _is_in_scope(path: Path) -> tuple[bool, str]:
    """Return (in_scope, layer_name) for a given file path."""
    parts = path.parts
    if "extensions" in parts and "builtin" in parts:
        return True, "extension"
    if "skills" in parts and "builtin" in parts:
        return True, "skill"
    if "core-plugins" in parts:
        return True, "plugin"
    return False, ""


def _is_waived(line: str, rule_id: str) -> bool:
    return f"nosemgrep: {rule_id}" in line


def _check_file(path: Path, source: str) -> list[str]:
    violations: list[str] = []
    in_scope, layer = _is_in_scope(path)
    if not in_scope:
        return violations

    is_init = path.name == "__init__.py"
    lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return violations  # syntax errors are someone else's job

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        raw_line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0] if module else ""

            # Rule: no core-backend internals
            if top in _CORE_BACKEND_PACKAGES and top not in ("extensions", "skills"):
                rule = "extension-no-core-internals"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] {layer} imports core "
                        f"module '{module}' — use autobot_shared instead  "
                        f"(waiver: # nosemgrep: {rule})"
                    )

            # Rule: no sibling extension imports (skip __init__.py)
            if not is_init and layer == "extension" and module.startswith("extensions.builtin."):
                rule = "extension-no-sibling-import"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] extension imports sibling "
                        f"'{module}' — use ExtensionManager hooks or "
                        f"autobot_shared  (waiver: # nosemgrep: {rule})"
                    )

            # Rule: no sibling skill imports (skip __init__.py)
            if not is_init and layer == "skill" and module.startswith("skills.builtin."):
                rule = "skill-no-sibling-import"
                if not _is_waived(raw_line, rule):
                    violations.append(
                        f"{path}:{lineno}: [{rule}] skill imports sibling "
                        f"'{module}' — share logic via autobot_shared  "
                        f"(waiver: # nosemgrep: {rule})"
                    )

    return violations


def main() -> int:
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
    else:
        # pre-commit passes files via stdin when pass_filenames: false
        files = [Path(line.strip()) for line in sys.stdin if line.strip().endswith(".py")]

    all_violations: list[str] = []
    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        all_violations.extend(_check_file(filepath, source))

    for v in all_violations:
        print(v)

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
