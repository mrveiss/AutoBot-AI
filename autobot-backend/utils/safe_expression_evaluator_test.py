# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for SafeExpressionEvaluator subscript support (GH#9036)."""

import pytest

from utils.safe_expression_evaluator import safe_evaluator


class TestSubscript:
    def test_dict_subscript(self):
        ctx = {"results": {"step1": {"exit_code": 0}}}
        assert safe_evaluator.evaluate("results['step1']['exit_code']", ctx) == 0

    def test_subscript_in_comparison(self):
        ctx = {"results": {"step1": {"exit_code": 0}}}
        assert safe_evaluator.evaluate("results['step1']['exit_code'] == 0", ctx) is True

    def test_list_index(self):
        ctx = {"items": [10, 20, 30]}
        assert safe_evaluator.evaluate("items[1]", ctx) == 20

    def test_missing_key_raises_valueerror(self):
        with pytest.raises(ValueError):
            safe_evaluator.evaluate("results['nope']", {"results": {}})


class TestSandboxEscapeBlocked:
    def test_attribute_access_rejected(self):
        # __class__/__bases__ escape relies on ast.Attribute, which is unsupported.
        with pytest.raises(ValueError):
            safe_evaluator.evaluate("results.__class__.__bases__", {"results": {}})

    def test_dunder_subclasses_rejected(self):
        with pytest.raises(ValueError):
            safe_evaluator.evaluate("().__class__.__bases__[0].__subclasses__()", {})

    def test_import_rejected(self):
        with pytest.raises(ValueError):
            safe_evaluator.evaluate("__import__('os').getcwd()", {})
