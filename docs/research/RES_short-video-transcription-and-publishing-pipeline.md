# Short-video transcription and multi-channel publishing pipeline

**Date:** 2026-11-26 · **Type:** technical research (anonymized) · **Baseline:** `origin/main` @ a7554bcbfb · **Issues:** #22302, #22303

## Source analysis (anonymized)

The reference work is a small commercial SaaS for short vertical videos, aimed at a regional-language market. The user uploads a clip; the service transcribes it, lets the user edit the video by cutting words from the transcript, generates a title, description and tags, renders subtitles and a cover, then publishes to several social networks at once or schedules the post. Closed source, no public API, webhooks or SSO; the product is reachable only after sign-up.

Patterns of note:
- **Seven-step wizard per item** (text → audio → visuals → subtitles → title → cover → ready), with skippable steps and free back-navigation.
- **One human review point.** Everything is generated automatically; the user edits once, then publishes.
- **Transcript-quality flags.** A language model marks words that are likely transcription errors.
- **Per-destination text limits.** Generated text is cut to each destination's limits.
- **Workspaces** per brand or project, with an admin and user role and a per-user "may publish" permission.
- **Outsourced edges.** Speech recognition, text generation and the publishing step itself are bought from third-party services.

Hidden costs: every publishing destination brings app review, OAuth token custody, quotas and API changes, which is why the reference work buys publishing from an aggregator. Audio goes to a hosted speech vendor, and session recordings can capture customer content.

## AutoBot comparison

Rule applied: anything adopted is rebuilt on AutoBot's own stack. The reference work is never installed, vendored or run.

### Already stronger in AutoBot
- Messaging channels: WhatsApp Cloud API inbound and outbound (`integrations/whatsapp_integration.py`, `api/whatsapp.py`), Telegram (`api/telegram_bot.py`, `services/telegram_polling.py`), and Slack, Teams and Discord adapters (`integrations/messaging_adapters.py`). The reference work has none.
- Latvian speech recognition with dedicated providers and a fallback chain (`voice_processing/providers/lv/`, `voice_processing/providers/registry_init.py`), and a Latvian hallucination filter (`voice_processing/hallucination_filter.py`).
- Typed approval gates and an outbound egress governor (`models/approval.py`, `services/gateway/egress_governor`), against a single "may publish" toggle.
- Subtitle export (`transcriber/export/srt_export.py`, `vtt_export.py`) and image generation (`plugins/core-plugins/image-generation-plugin`) already exist.
- Self-hosted by default: no audio has to leave the host.

### Defects found while comparing
- **Audio language detection reads only the filename.** `voice_processing/language_detection.py` `_extract_text_sample` matches language tokens in the filename. Otherwise it returns `None`, and the default language is forced onto the speech model. Uploaded Latvian audio with a neutral name is transcribed as the default language → #22302.
- **The calendar skill reports success without a calendar.** `skills/builtin/calendar_integration.py` create, list and availability return `success: True, status: "queued"` and call nothing. A Microsoft 365 calendar client already exists in `integrations/microsoft365_integration.py`. No Google Calendar or CalDAV client exists → #22303.

### Adoptable, not filed
- Title, description and tag prompts with per-destination length caps in `transcriber/ai/prompts.py` (today only `summarize`, `key_facts`, `protocol` exist). Effort: trivial.
- A per-word "likely mistranscribed" flag on transcripts. This needs word-level confidence from the speech provider.
- One pre-publish review payload (caption, cover, destinations). Build it only on the consolidated approval service (#17043), not as another approval surface (#13421).

### Rejected on hidden costs
- Native publishing to social networks: there is no publish client today, each destination carries a permanent maintenance cost, and it is outside AutoBot's scope as an assistant and Company OS.
- Video rendering and editing (transcript-based cuts, subtitle burn-in, overlays): a change of product category, not a gap.

## Linked issues

- #22302 bug(voice): audio language detection only reads the filename — uploaded Latvian audio is transcribed as the default language
- #22303 bug(skills): calendar skill reports success for create, list and availability but never calls a calendar
