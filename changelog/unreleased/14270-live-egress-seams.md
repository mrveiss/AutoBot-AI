---
type: security
scope: integrations
issue: 14270
pr: 0
---
Outbound sends on the live channels (Telegram, WhatsApp, Slack/Discord/Teams) now pass the egress governance stage, so every message to a real person is recorded and can be gated; operational alerts are audited but never blocked.
- Cover the sibling senders review found ungoverned: Telegram `send_photo` and
  `send_document` (both reachable from the agent-response dispatcher), the Teams
  webhook endpoint, and the SMTP notification channel. The Telegram gate is now
  one helper rather than a check copied per method.
