# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one answer to "is this file name a test file?" (#20493).

The repo co-locates tests (``foo_test.py`` beside ``foo.py``), so a directory name
alone never marks them. Name conventions recognised:

* Python: ``test_*.py``, ``*_test.py`` (so ``test_.py`` and ``_test.py`` too), ``tests.py``,
  ``conftest.py`` (unless ``include_conftest=False``)
* JS/TS/Vue (``include_js=True``, the default): ``*.test.<ext>``, ``*.spec.<ext>``

The rule is by NAME, so a production module called ``test_*.py`` is classed as a
test: rename it rather than special-casing it here. ``attestation.py``,
``latest_result.py`` and ``testing_utils.py`` are not matched.

Directory-based rules (``tests/``, ``archive/``...) differ per caller and stay with
the caller; they combine with this function, they do not copy it.

Callers that stay separate on purpose: the entries in
``repo_tests/test_name_predicate_baseline_21078.py`` (each with its reason, e.g. the
system-interpreter hook and ``audit_unwired_trackers``); the rest of the hand-written copies are
tracked in #21161.
"""

import re

# ``.*`` not ``.+``: ``test_.py`` and ``_test.py`` are tests, as the older ``startswith("test_")`` /
# ``endswith("_test")`` rules had it (the meta-agent target refusal depends on that).
_PY_TEST_RE = re.compile(r"^(test_.*|.*_test|tests|conftest)\.py$")
_PY_TEST_NO_CONFTEST_RE = re.compile(r"^(test_.*|.*_test|tests)\.py$")
_JS_TEST_RE = re.compile(r"^.+\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|vue)$")


def is_test_filename(filename: str, *, include_js: bool = True, include_conftest: bool = True) -> bool:
    """True when the base name (any case) follows a test-file convention.

    ``include_conftest=False`` leaves ``conftest.py`` out: a tool that scans it as real code
    (hooks, fixtures and env handling are production-shaped) passes this so the move to the
    canonical rule does not drop it from the tool's population (#21078).
    """
    name = filename.rsplit("/", 1)[-1].lower()
    py_re = _PY_TEST_RE if include_conftest else _PY_TEST_NO_CONFTEST_RE
    return py_re.match(name) is not None or (include_js and _JS_TEST_RE.match(name) is not None)
