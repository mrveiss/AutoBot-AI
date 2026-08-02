# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for Issue #13217 — interpret_terminal_command died on
``ModelConstants.DEFAULT_NUM_CTX``.

``DEFAULT_NUM_CTX`` is declared on ``ModelConfig``; ``ModelConstants`` is the
adjacent class in the same module and has no ``NUM_CTX`` attribute at all.
``_get_interpretation_llm_options`` read it off the wrong class, so every
natural-language terminal interpretation raised::

    AttributeError: type object 'ModelConstants' has no attribute 'DEFAULT_NUM_CTX'

Before the fix ``test_interpretation_options_include_num_ctx`` raises that
AttributeError. ``test_num_ctx_is_owned_by_model_config`` pins the ownership
so the constant cannot silently migrate back.
"""

from chat_workflow.llm_handler import LLMHandlerMixin
from constants.model_constants import ModelConfig, ModelConstants


def test_num_ctx_is_owned_by_model_config() -> None:
    """DEFAULT_NUM_CTX lives on ModelConfig, never on ModelConstants."""
    assert isinstance(ModelConfig.DEFAULT_NUM_CTX, int)
    assert not hasattr(ModelConstants, "DEFAULT_NUM_CTX")


def test_interpretation_options_include_num_ctx() -> None:
    """The interpretation options build without AttributeError.

    ``_get_interpretation_llm_options`` does not touch ``self``, so an
    uninitialised instance is enough to exercise the real attribute read
    without constructing the full workflow manager.
    """
    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)

    options = handler._get_interpretation_llm_options()

    assert options["num_ctx"] == ModelConfig.DEFAULT_NUM_CTX
