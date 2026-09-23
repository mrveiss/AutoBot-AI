---
type: fix
scope: backend
issue: 14893
pr: 0000
---
api/live_events.py's `_handle_subscribe` carried its own inline copy of the per-channel-prefix authorization rules, separate from `_authorize_channel` (the function the command path uses via `dispatch_command`). The two drifted within a single commit: #14826 tightened `_authorize_channel` to deny an unrecognised channel prefix by default, but the inline copy in `_handle_subscribe` stayed default-allow, so an unrecognised prefix was denied on the command path and allowed on the subscribe path (not currently exploitable only because `_is_valid_channel` separately rejects unknown prefixes before delivery). `_handle_subscribe` now calls `_authorize_channel` directly instead of re-implementing its rules, so the two paths cannot diverge again.
