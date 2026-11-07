# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is this file name a test file? (#20493)

The repo co-locates tests (``foo_test.py`` beside ``foo.py``), so a directory name
alone never marks them, and an analysis that scores them as production code
reports their long fixtures and sequential awaits as defects.
"""

import re

_TEST_FILE_RE = re.compile(
    r"^(test_.+|.+_test|conftest)\.py$" r"|^.+\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|vue)$" r"|^.+_test\.(js|ts)$"
)


def is_test_filename(filename: str) -> bool:
    """True for a lowercased base name that follows a test-file convention."""
    return _TEST_FILE_RE.match(filename) is not None
