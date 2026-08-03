# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified Tools Package

This package provides a centralized tool registry that eliminates duplication
between the standard orchestrator and LangChain orchestrator implementations.

Namespace note (#13086): the repo has two `tools/` directories —
`/autobot-backend/tools/` (this one: production tool registry / parallel
executor) and `/tools/` at the repo root (lint hooks, canonical-check runner).
Both must be reachable as `tools.X` no matter which one Python binds to the
`tools` name first. The root package already calls `pkgutil.extend_path`; this
one must do the same, otherwise a test session that imports
`tools.tool_registry` before `tools.lint` pins `tools.__path__` to this
directory alone and every `tools.lint.*` import fails with ModuleNotFoundError.
`extend_path` only appends `tools/` directories that are actually on sys.path,
so production deployments (repo root not on sys.path) are unaffected.
"""

import pkgutil

from .code_interpreter import CODE_INTERPRETER_SCHEMA, execute_code
from .tool_registry import ToolRegistry, get_tool_registry

__path__ = pkgutil.extend_path(__path__, __name__)

__all__ = ["CODE_INTERPRETER_SCHEMA", "ToolRegistry", "execute_code", "get_tool_registry"]
