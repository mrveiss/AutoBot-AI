# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every UI locale needs a response-language name (#18442)."""

import importlib.util
import sys
from pathlib import Path

from autobot_shared.supported_languages import SUPPORTED_LANGUAGES

_REPO = Path(__file__).resolve().parent.parent
_LOCALES = _REPO / "autobot-frontend" / "src" / "i18n" / "locales"


def _locale_codes():
    return sorted(p.stem for p in _LOCALES.glob("*.json"))


def _load_prompt_manager():
    backend = str(_REPO / "autobot-backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    spec = importlib.util.spec_from_file_location("_pm_18442", _REPO / "autobot-backend" / "prompt_manager.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_locale_directory_is_not_empty():
    assert _locale_codes(), f"no locale files found under {_LOCALES}"


def test_every_frontend_locale_has_a_language_name():
    missing = [c for c in _locale_codes() if c not in SUPPORTED_LANGUAGES]
    assert not missing, f"locales without a SUPPORTED_LANGUAGES entry: {missing}"


def test_language_instruction_names_the_language_not_the_code():
    pm = _load_prompt_manager()
    assert "Latvian (lv)" in pm.get_language_instruction("lv")
    assert "Polish (pl)" in pm.get_language_instruction("pl")


def test_prompt_manager_reads_the_shared_map():
    assert _load_prompt_manager().SUPPORTED_LANGUAGES is SUPPORTED_LANGUAGES
