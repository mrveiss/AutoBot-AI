# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Load the real ``code_intelligence.pattern_analysis`` package past the conftest stub (#22157).

The top-level conftest replaces ``code_intelligence.pattern_analysis`` with a
MagicMock. A test that must exercise the real modules loads them under a private
package name instead. Moved unchanged from three test files that each carried a
copy, differing only in that name; each caller still passes its own.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_real_pattern_analysis_package(base: Path, pkg_name: str) -> ModuleType:
    """Load the pattern_analysis submodules from ``base`` under ``pkg_name``, in dependency order."""
    if pkg_name not in sys.modules:
        pkg = ModuleType(pkg_name)
        pkg.__path__ = [str(base)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
        for sub in (
            "types",
            "cancellation",
            "complexity_analyzer",
            "refactoring_generator",
            "regex_detector",
            "storage",
            "analyzer",
        ):
            spec = importlib.util.spec_from_file_location(f"{pkg_name}.{sub}", base / f"{sub}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"{pkg_name}.{sub}"] = module
            spec.loader.exec_module(module)
            setattr(pkg, sub, module)

    return sys.modules[pkg_name]
