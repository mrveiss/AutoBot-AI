# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge UI's default fact category mirrors the backend's canonical one (#21921).

The backend names it ``CategoryDefaults.GENERAL`` (``'general'``); the UI shows the same category
as ``DEFAULT_FACT_CATEGORY`` (``'General'``). The frontend cannot import Python, so this test reads
the TypeScript constant and fails when the two stop naming the same category.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from autobot_shared.category_defaults import CategoryDefaults

MAPPING = repo_root() / "autobot-frontend" / "src" / "models" / "repositories" / "knowledgeFactMapping.ts"
_DECLARATION = re.compile(r"""^export const DEFAULT_FACT_CATEGORY = (['"])(?P<value>[^'"]+)\1\s*$""", re.MULTILINE)


def ui_default_category(source: str) -> str | None:
    match = _DECLARATION.search(source)
    return match.group("value") if match else None


def test_the_ui_default_category_is_the_backend_default_in_display_case() -> None:
    value = ui_default_category(MAPPING.read_text(encoding="utf-8"))
    assert value is not None, f"no DEFAULT_FACT_CATEGORY declaration in {MAPPING.name}"
    assert value.lower() == CategoryDefaults.GENERAL


def test_the_reader_finds_a_declaration_and_reports_a_missing_one() -> None:
    assert ui_default_category("export const DEFAULT_FACT_CATEGORY = 'Docs'\n") == "Docs"
    assert ui_default_category("const DEFAULT_FACT_CATEGORY = 'x'\n") is None
