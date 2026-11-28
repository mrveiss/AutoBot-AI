# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Single source of truth for the response languages AutoBot can be asked to use.

Leaf module (no imports) so both ``prompt_manager`` and
``services.personality_service`` can read it without a circular import.
Every UI locale under ``autobot-frontend/src/i18n/locales/`` must have an
entry here (enforced by ``supported_languages_test.py``).

Related Issue: #18442
"""

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "hi": "Hindi",
    "he": "Hebrew",
    "fa": "Persian",
    "ur": "Urdu",
    "lv": "Latvian",
    "pl": "Polish",
}
