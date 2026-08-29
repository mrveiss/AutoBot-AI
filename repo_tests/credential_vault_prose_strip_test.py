# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
""":func:`strip_prose` blanks prose without touching an executable string (#15280).

``credential_vault_resolution_guard_test.py`` trusts this module to remove
false-positive prose matches without also erasing the one string shape that IS a
real credential read -- a ``getattr(cfg, "field", ...)`` field-name literal. Both
are proven here in isolation so a regression in either shows up at this module's
own test, not buried inside the much larger guard suite.
"""

from __future__ import annotations

import pytest
from repo_tests.credential_vault_prose_strip import UnparseableSourceError, strip_prose


def test_a_module_docstring_is_blanked_but_line_numbers_are_preserved() -> None:
    text = '"""Mentions cfg.llm.openai_api_key in prose."""\n\nx = 1\n'
    stripped = strip_prose(text)
    assert "openai_api_key" not in stripped
    assert stripped.count("\n") == text.count("\n")
    assert stripped.splitlines()[2] == "x = 1"


def test_a_comment_is_blanked() -> None:
    text = "x = 1  # mentions cfg.llm.openai_api_key\n"
    assert "openai_api_key" not in strip_prose(text)


def test_a_getattr_field_name_literal_survives_stripping() -> None:
    """The #15267 shape: a string used as a call argument, not a floating
    statement, is code -- not prose -- and must not be blanked.
    """
    text = 'brave_key = getattr(config, "brave_search_api_key", "")\n'
    assert strip_prose(text) == text


def test_a_file_that_fails_to_tokenize_raises_rather_than_returning_something() -> None:
    with pytest.raises(UnparseableSourceError):
        strip_prose("def f(:\n    pass\n")
