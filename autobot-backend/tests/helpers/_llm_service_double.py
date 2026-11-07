# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An ``LLMService`` double that only accepts what the real class defines (#19649).

``testkit.real_llm_service`` loads the genuine class (the conftest stubs the public
module with a mock, which ``create_autospec`` cannot spec).
"""

from functools import lru_cache
from unittest.mock import create_autospec

from testkit.real_llm_service import load_real_llm_service


@lru_cache(maxsize=1)
def real_llm_service_class() -> type:
    """The genuine ``LLMService`` class."""
    return load_real_llm_service().LLMService


def make_llm_service_double():
    """An instance double: calling a method ``LLMService`` lacks raises ``AttributeError``."""
    return create_autospec(real_llm_service_class(), instance=True)
