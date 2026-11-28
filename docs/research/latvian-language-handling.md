# Research: Latvian-language handling in AutoBot

Status: complete (2026-10-12). Issues: #18442, #18443.

## What already works

| Area | AutoBot evidence |
|---|---|
| Latvian STT routing | `voice_processing/providers/registry_init.py:69-95` — dedicated local Latvian engine (priority 10), external Latvian provider (5, declared primary-external per #17778), generic fallback (-10) |
| STT phantom-text filter | `voice_processing/hallucination_filter.py:93,125` — lv credit-string and outro denylists |
| Language detection | `voice_processing/language_detection.py` — filename-token hints (`lv`, `lat`, `latvian`, `latviesu`) + text detector |
| Browser STT locale | `autobot-frontend/src/composables/useVoiceConversation.ts:302-318` — `lv → lv-LV` |
| UI i18n | `autobot-frontend/src/i18n/locales/lv.json` (one of 11 locales) |
| Per-language voice choice | `services/personality_service.py:366` `resolve_voice_id(..., language)` reads `profile.voice_ids[language]` |

## Gaps

1. **Reply-language map has no `lv`** → #18442.
   `prompt_manager.py:1431` and the canonical `services/personality_service.py:38`
   `SUPPORTED_LANGUAGES` omit `lv` (and `pl`) although both are UI locales.
   `get_language_instruction("lv")` (`prompt_manager.py:1467`) therefore emits "respond in lv (lv)"
   instead of "Latvian (lv)" — a bare code is a weaker instruction for smaller LLMs. The two copies
   already drift (13 vs 16 entries). Fix: add `lv`/`pl`, collapse to one canonical copy. Effort:
   trivial.

2. **No Latvian speech synthesis** → #18443 (child of #17778).
   The TTS worker engine, pocket-tts (`autobot-tts-worker/requirements.txt`), publishes support for
   en, fr, de, pt, it, es only — no Latvian (checked 2026-10-12). The legacy gTTS path
   (`voice_interface.py:601`) reads a static `gtts_lang` config defaulting to `en`, not the request
   language, and is one of #17778's unwired duplicates, so it is not the fix site.
   Direction: an offline `lv_LV` neural voice **inside** the canonical worker — a separate synthesis
   engine would conflict with #17778's consolidation. Cloud neural voices reached through unofficial
   clients are rejected (terms/availability risk, every reply leaves the host). Effort: moderate.

## Files affected

- `autobot-backend/services/personality_service.py:38` — add `lv: "Latvian"`, `pl: "Polish"`.
- `autobot-backend/prompt_manager.py:1431` — replace the duplicated map with the canonical one.
- `autobot-tts-worker/` — Latvian voice selection when `language == "lv"`, under #17778.

## Linked issues

Issues this research produced or is the analysis for (#18967). Each one links back to this document.

- #18442 — bug(i18n): response-language map lacks lv and pl — Latvian users get "respond in lv (lv)" (closed)
- #18443 — feat(voice): Latvian speech synthesis — the TTS worker engine does not support lv
