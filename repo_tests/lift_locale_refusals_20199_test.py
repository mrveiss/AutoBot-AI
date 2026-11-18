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
    assert lift.collect_refusals(flat, by_text, de, src_en) == {
        "short": ["unit.other"],
        "no-source": [],
        "no-translation": [],
        "tie": [],
    }


def test_shipped_mappings_point_at_real_matching_keys() -> None:
    from autobot_shared.locale_tree import flatten

    slm = flatten(json.loads((repo_root() / "autobot-slm-frontend/src/locales/en.json").read_text(encoding="utf-8")))
    main = flatten(json.loads((repo_root() / "autobot-frontend/src/i18n/locales/en.json").read_text(encoding="utf-8")))
    for app_key, main_key in lift.KEY_MAPPINGS.items():
        assert slm[app_key] == main[main_key]


_DURATION_KEYS = (
    "agents.processMonitorTab.durationSeconds",
    "agents.processMonitorTab.durationMinutes",
)


def _ar_labels_not_translated(mappings, en: dict, ar: dict) -> list[str]:
    """The mapped keys whose Arabic label is missing, blank, not a string, or equal to the English one."""
    return [key for key in mappings if not (isinstance(ar.get(key), str) and ar[key].strip()) or ar[key] == en.get(key)]


def test_the_duration_keys_are_mapped() -> None:
    """Removing a key must fail here, not silently stop the Arabic check covering it (#21314)."""
    assert set(_DURATION_KEYS) <= set(lift.KEY_MAPPINGS)


def test_the_arabic_check_passes_a_translated_label() -> None:
    assert _ar_labels_not_translated({"k": "m"}, {"k": "s"}, {"k": "ث"}) == []


def test_the_arabic_check_reports_a_missing_label() -> None:
    assert _ar_labels_not_translated({"k": "m"}, {"k": "s"}, {}) == ["k"]


def test_the_arabic_check_reports_a_blank_label() -> None:
    assert _ar_labels_not_translated({"k": "m"}, {"k": "s"}, {"k": "  "}) == ["k"]


def test_the_arabic_check_reports_a_label_equal_to_the_english() -> None:
    assert _ar_labels_not_translated({"k": "m"}, {"k": "s"}, {"k": "s"}) == ["k"]


def test_shipped_arabic_duration_labels_stay_translated() -> None:
    """A removed or English source label must not be retained silently (#21192)."""
    from autobot_shared.locale_tree import flatten

    base = repo_root() / "autobot-slm-frontend" / "src" / "locales"
    en = flatten(json.loads((base / "en.json").read_text(encoding="utf-8")))
    ar = flatten(json.loads((base / "ar.json").read_text(encoding="utf-8")))
    assert _ar_labels_not_translated(_DURATION_KEYS, en, ar) == []
    assert _ar_labels_not_translated(lift.KEY_MAPPINGS, en, ar) == []
