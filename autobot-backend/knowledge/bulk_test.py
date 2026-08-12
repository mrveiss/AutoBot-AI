# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``BulkOperationsMixin._parse_import_csv`` (#14047)."""

from constants.threshold_constants import CategoryDefaults
from knowledge.bulk import BulkOperationsMixin


def test_missing_category_defaults_to_general():
    mixin = BulkOperationsMixin()
    content = "fact_id,content,tags\n1,hello,foo\n"

    facts = mixin._parse_import_csv(content)

    assert facts[0]["metadata"]["category"] == CategoryDefaults.GENERAL


def test_explicit_category_overrides_default():
    mixin = BulkOperationsMixin()
    content = "fact_id,content,category,tags\n1,hello,security,foo\n"

    facts = mixin._parse_import_csv(content)

    assert facts[0]["metadata"]["category"] == "security"
