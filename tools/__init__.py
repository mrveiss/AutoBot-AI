# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Namespace-extending package init for `tools`.

The repo has two `tools/` directories:
  - `/tools/` at the repo root (lint hooks, canonical-check runner)
  - `/autobot-backend/tools/` (production tool registry / parallel executor)

Both must be reachable as `tools.X` regardless of which is found first on
sys.path. An empty `__init__.py` would mark `/tools/` as a regular package
and shadow `/autobot-backend/tools/`, breaking `from tools.parallel import …`
in production code. Using pkgutil.extend_path merges both directories into
one logical `tools` package.

Required for pytest's `--import-mode=importlib` to resolve
`tools.lint.canonical.*` when running from the repo root.
"""

import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)
