# Umbrella #9928 (integrations-plugins) — Verification Report (2026-06-23)

## Goal
Verify "umbrella #9928 issues fully solved."

## Member status — all 12 CLOSED
- Original 10: #9019, #9003, #9004, #9011, #9006, #9007, #9010, #9022, #9023, #9016
- Triage-delta: #10267, #10294 (both delivered by PR #10442, merged `4d5f464bd`, auto-closed)

## Finding: closed ≠ solved
PR #10442 merged the #10267 inbound-WhatsApp-media path with two real defects in
`_route_to_chat_and_reply`, so media routing did not actually work:

1. **Crash (severe):** caption-less media built `ChatMessage(content="")`, but
   `content` is `min_length=1` → `ValidationError` → uncaught in the webhook loop →
   the whole inbound batch dropped. The common case (voice/photo/sticker with no
   caption) never routed.
2. **Silent persistence loss:** raw downloaded bytes were stored in chat metadata
   (`file_bytes`); persistence does `json.dumps` with no `default=str` → `TypeError`
   (swallowed) → every media message failed to persist to history.

## Action
- Filed #10481; fixed both in PR #10482 (placeholder content for caption-less media;
  lightweight references — media_id/file_type/file_size/mime_type — mirroring
  telegram_adapter's has_file pattern instead of raw bytes). Added regression tests
  (`api/whatsapp_test.py`, 14 passed). CI green; awaiting owner merge.
- Filed #10483: Telegram channel (#9006) has the same caption-less `ValidationError`
  crash (`telegram_bot.py:191`).
- Posted the finding on PR #10442; updated umbrella #9928 checklist + triage delta.

## Remaining for full closure
- Merge PR #10482 (owner action — cannot self-approve own PR).
- #10483 (Telegram) — separate follow-up.
