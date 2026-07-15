# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11019 — LLMType is a str-Enum, so a member is interchangeable with its string
value. This is what makes migrating call sites from raw strings to LLMType.X safe:
router dict-lookups keyed by the string still resolve and ``== "extraction"``
comparisons (incl. existing test assertions) keep holding."""

from llm_shared.types import LLMType


def test_llmtype_is_str_subclass():
    assert issubclass(LLMType, str)
    assert isinstance(LLMType.EXTRACTION, str)


def test_llmtype_member_equals_its_value():
    assert LLMType.EXTRACTION == "extraction"
    assert LLMType.ANALYSIS == "analysis"
    assert LLMType.EXTRACTION.value == "extraction"


def test_llmtype_resolves_as_dict_key_with_raw_string():
    # A dict keyed by the raw string still resolves via the enum member and vice
    # versa — the property the model-tier router relies on.
    by_string = {"extraction": 1, "analysis": 2}
    assert by_string[LLMType.EXTRACTION] == 1
    by_enum = {LLMType.EXTRACTION: 1}
    assert by_enum["extraction"] == 1


def test_all_members_roundtrip():
    for member in LLMType:
        assert LLMType(member.value) is member
        assert member == member.value
