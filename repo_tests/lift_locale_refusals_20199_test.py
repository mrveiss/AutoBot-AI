# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The locale generator names why a key keeps its English (#20199)."""

from __future__ import annotations

import importlib.util
import json

from repo_tests._paths import repo_root

_SPEC = importlib.util.spec_from_file_location(
    "lift_locale_translations", repo_root() / "scripts" / "lift_locale_translations.py"
)
lift = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lift)


def test_reasons_are_distinguished() -> None:
    assert lift.refusal_reason("Cancel", ["Abbrechen"] * 4) is None
    assert lift.refusal_reason("Target", ["Cible", "Objectif"]) == "tie"
    assert lift.refusal_reason("Target", ["Target"]) == "no-translation"


def test_collect_refusals_groups_by_reason() -> None:
    app = {"a": "OK", "b": "Unknown text", "c": "Target", "d": "Settings"}
    by_text = {"Target": ["x", "y"], "Settings": ["z"]}
    locale = {"x": "Cible", "y": "Objectif", "z": "Paramètres"}
    got = lift.collect_refusals(app, by_text, locale)
    assert got == {"short": ["a"], "no-source": ["b"], "no-translation": [], "tie": ["c"]}


def test_overview_is_settled_in_de_and_es() -> None:
    """The main-app 'Overview' keys that disagreed now share one word."""
    base = repo_root() / "autobot-slm-frontend" / "src" / "locales"
    for locale, word in (("de", "Übersicht"), ("es", "Resumen")):
        tree = json.loads((base / f"{locale}.json").read_text(encoding="utf-8"))
        assert tree["performanceView"]["tabs"]["overview"] == word
