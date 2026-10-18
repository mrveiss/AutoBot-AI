# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one Python-file collector shared by the code-intelligence analyzers (#18731).

The anti-pattern suite, the clone detector and the pattern analyzer each
carried their own copy of this walk; they now delegate here.
"""

from pathlib import Path
from typing import Iterable, List


def collect_python_files(directory: str, exclude_dirs: Iterable[str]) -> List[str]:
    """Return sorted ``*.py`` paths under *directory*, skipping any path with an excluded part."""
    excluded = set(exclude_dirs)
    return sorted(str(py_file) for py_file in Path(directory).rglob("*.py") if not excluded.intersection(py_file.parts))
