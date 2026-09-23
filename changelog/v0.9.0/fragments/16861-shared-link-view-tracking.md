---
type: feature
scope: backend,frontend
issue: 16861
pr: 0000
---
Shared chat links (GH#8996) gain the two fields their own "what users want" list named but never shipped: a per-link view count / last-accessed timestamp, and an optional `require_login` restriction. `ChatSharedLink` gets three new columns (migration `20260919_094`, rebased onto the current chain head after the original draft on a rescued stash pointed at a since-forked `down_revision`), `api/chat_shared_links.py`'s access paths increment the counter and enforce the login requirement (401, not silently served), and `ShareConversationDialog.vue` exposes the checkbox and shows both stats on the created link.
