---
type: security
scope: secrets
issue: 16426
pr: 0
---
Infrastructure host connection metadata (hostnames, ports, usernames) and host deletion are now admin-only via `GET`/`DELETE /api/infrastructure/hosts`; any authenticated user could previously list or delete every configured host. The Secrets UI now hides the Infrastructure Hosts category and template from non-admins. The OpenAI, Anthropic and Slack credential templates now pre-fill the exact runtime key name (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`) instead of a display label, so a key saved through those templates is actually mirrored into the System vault and reachable at runtime (#16427).
