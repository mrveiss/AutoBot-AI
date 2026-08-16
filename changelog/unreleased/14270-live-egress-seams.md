---
type: security
scope: integrations
issue: 14270
pr: 0
---
Outbound sends on the live channels (Telegram, WhatsApp, Slack/Discord/Teams) now pass the egress governance stage, so every message to a real person is recorded and can be gated; operational alerts are audited but never blocked.
