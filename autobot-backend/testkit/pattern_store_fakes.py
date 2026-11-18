# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stand-ins for the pattern-analysis package a test reaches through a function-local import (#21327).

The suite's ``conftest`` registers ``code_intelligence.pattern_analysis`` as a bare stub package
(its real ``__init__`` chain is heavy), and that stub has no ``storage`` submodule. A code path
that imports ``CodePatternAnalyzer`` or ``search_similar_patterns`` inside the function therefore
resolves whatever ``sys.modules`` holds at call time -- the stub, a real package, or nothing --
and a ``patch("...pattern_analysis.storage.X")`` string cannot change that: it walks attributes
on the stub and patches a throwaway. Installing both modules under their dotted names makes the
import resolve to the fakes whichever of those is present, and ``monkeypatch.setitem`` restores
the previous entry, so no test leaves anything behind for the next one in the worker.
"""

import sys
from types import ModuleType
from typing import Any

import pytest

PACKAGE = "code_intelligence.pattern_analysis"
STORAGE = f"{PACKAGE}.storage"


def install_pattern_fakes(monkeypatch: pytest.MonkeyPatch, *, analyzer: Any, search: Any) -> None:
    """Make ``from code_intelligence.pattern_analysis[.storage] import ...`` yield these objects."""
    package, storage = ModuleType(PACKAGE), ModuleType(STORAGE)
    package.__path__ = []  # a package, so the dotted submodule import below is legal
    package.CodePatternAnalyzer = analyzer
    storage.search_similar_patterns = search
    monkeypatch.setitem(sys.modules, PACKAGE, package)
    monkeypatch.setitem(sys.modules, STORAGE, storage)
