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


def _fixture():
    app = {"unit": {"sec": "s", "other": "s"}, "word": "Target", "plain": "Untranslated text"}
    src_en = {"w.sec": "s", "w.x": "s", "w.word": "Target", "w.plain": "Untranslated text"}
    by_text = {}
    for k, v in src_en.items():
        by_text.setdefault(v, []).append(k)
    de = {"w.sec": "Sek", "w.x": "Zzz", "w.word": "Ziel", "w.plain": "Untranslated text"}
    return app, by_text, de, src_en


def test_short_source_lifts_only_through_an_explicit_key_mapping(monkeypatch) -> None:
    monkeypatch.setattr(lift, "KEY_MAPPINGS", {"unit.sec": "w.sec"})
    app, by_text, de, src_en = _fixture()
    out = lift.build_locale(app, by_text, de, src_en)
    assert out["unit"]["sec"] == "Sek"  # mapped: lifted despite one letter
    assert out["unit"]["other"] == "s"  # unmapped short source: still English
    assert out["word"] == "Ziel"  # translated in the main app: carried
    assert out["plain"] == "Untranslated text"  # untranslated there: English


def test_mapping_is_ignored_when_the_main_app_source_drifted(monkeypatch) -> None:
    monkeypatch.setattr(lift, "KEY_MAPPINGS", {"unit.sec": "w.sec"})
    app, by_text, de, src_en = _fixture()
    src_en["w.sec"] = "sec"
    assert lift.build_locale(app, by_text, de, src_en)["unit"]["sec"] == "s"


def test_refusals_no_longer_list_a_mapped_key(monkeypatch) -> None:
    monkeypatch.setattr(lift, "KEY_MAPPINGS", {"unit.sec": "w.sec"})
    app, by_text, de, src_en = _fixture()
    flat = {"unit.sec": "s", "unit.other": "s"}
    assert lift.collect_refusals(flat, by_text, de, src_en)["short"] == ["unit.other"]


def test_shipped_mappings_point_at_real_matching_keys() -> None:
    from autobot_shared.locale_tree import flatten

    slm = flatten(json.loads((repo_root() / "autobot-slm-frontend/src/locales/en.json").read_text(encoding="utf-8")))
    main = flatten(json.loads((repo_root() / "autobot-frontend/src/i18n/locales/en.json").read_text(encoding="utf-8")))
    for app_key, main_key in lift.KEY_MAPPINGS.items():
        assert slm[app_key] == main[main_key]
