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


def test_an_implicitly_concatenated_floating_docstring_is_blanked_in_full() -> None:
    """#15285 shape 2: two adjacent STRING tokens, not STRING-then-NEWLINE."""
    text = '"Mentions cfg.llm.openai_api_key " "in prose."\n\nx = 1\n'
    stripped = strip_prose(text)
    assert "openai_api_key" not in stripped
    assert stripped.count("\n") == text.count("\n")


def test_a_paren_wrapped_multiline_concatenated_docstring_is_blanked_in_full() -> None:
    """#15285: parens solely grouping a multi-line implicit concatenation are
    still recognised by Python as a docstring, so the whole run must go too.
    """
    text = '(\n    "Mentions cfg.llm.openai_api_key "\n    "across two lines."\n)\n\nx = 1\n'
    stripped = strip_prose(text)
    assert "openai_api_key" not in stripped
    assert stripped.count("\n") == text.count("\n")


def test_a_floating_fstring_is_blanked_as_prose() -> None:
    """#15285 shape 1: under PEP 701 (3.12+) an f-string is FSTRING_START /
    FSTRING_MIDDLE / FSTRING_END, never a single STRING token -- this must be
    blanked identically to 3.10, where it tokenizes as one STRING.
    """
    text = 'f"Mentions cfg.llm.openai_api_key: {1}"\n\nx = 1\n'
    stripped = strip_prose(text)
    assert "openai_api_key" not in stripped
    assert stripped.count("\n") == text.count("\n")


def test_a_call_argument_dict_value_and_assignment_rhs_all_survive_stripping() -> None:
    """Only floating statements are prose; a string in expression position is
    code and must never be blanked, on every shape #15285 adds handling for.
    """
    call_arg = 'log("openai_api_key present")\n'
    dict_value = 'cfg = {"key": "openai_api_key"}\n'
    assignment_rhs = 'msg = "openai_api_key" "leaked"\n'
    assert strip_prose(call_arg) == call_arg
    assert strip_prose(dict_value) == dict_value
    assert strip_prose(assignment_rhs) == assignment_rhs


def test_a_paren_wrapped_concatenation_in_expression_position_survives_stripping() -> None:
    """`_paren_wrapped_run` is the riskiest branch added for #15285 -- it exists
    to blank a *floating* paren-wrapped literal run, but parens also appear
    constantly in expression position, where the run must NOT be blanked. Every
    other survival case here reaches its check with ``at_stmt_start`` already
    ``False`` before a STRING is seen; these two put the paren-wrapped run
    itself inside a call argument and an assignment RHS, so they are the ones
    that actually exercise `_paren_wrapped_run`'s own guard rather than never
    reaching it. An over-blanking regression here would erase real code
    silently -- it would look like an ordinary false-positive cleanup, not a
    bug -- which is the failure mode this test exists to catch.
    """
    call_arg = 'f(("openai_api_key" "present"))\n'
    assignment_rhs = 'x = ("openai_api_key" "leaked")\n'
    assert strip_prose(call_arg) == call_arg
    assert strip_prose(assignment_rhs) == assignment_rhs
