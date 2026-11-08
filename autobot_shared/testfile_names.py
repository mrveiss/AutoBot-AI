# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one answer to "is this file name a test file?" (#20493).

The repo co-locates tests (``foo_test.py`` beside ``foo.py``), so a directory name
alone never marks them. Name conventions recognised:

* Python: ``test_*.py``, ``*_test.py``, ``tests.py``, ``conftest.py``
* JS/TS/Vue (``include_js=True``, the default): ``*.test.<ext>``, ``*.spec.<ext>``

The rule is by NAME, so a production module called ``test_*.py`` is classed as a
test: rename it rather than special-casing it here. ``attestation.py``,
``latest_result.py`` and ``testing_utils.py`` are not matched.

Directory-based rules (``tests/``, ``archive/``...) differ per caller and stay with
the caller; they combine with this function, they do not copy it.

Callers that stay separate (an open PR touches them; tracked as a follow-up in
#20493): ``api_endpoint_scanner._is_test_file``,
``config_duplication_detector._is_test_or_archive`` and
``TestingPatternAnalyzer.is_test_file`` (its patterns are caller-configurable).
"""

import re

_PY_TEST_RE = re.compile(r"^(test_.+|.+_test|tests|conftest)\.py$")
_JS_TEST_RE = re.compile(r"^.+\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|vue)$")


def is_test_filename(filename: str, *, include_js: bool = True) -> bool:
    """True when the base name (any case) follows a test-file convention."""
    name = filename.rsplit("/", 1)[-1].lower()
    return _PY_TEST_RE.match(name) is not None or (include_js and _JS_TEST_RE.match(name) is not None)
