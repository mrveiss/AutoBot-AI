---
tags: [type/reference, status/current]
date: 2026-10-12
---

# Tool Integrations — Base URLs and Egress

Applies to the admin-configured tool integrations (Jenkins, GitLab, CircleCI Server, GitHub, Jira, Bitbucket Cloud, Slack, Discord, Teams, Trello, Asana, Notion, Microsoft 365, Datadog, New Relic, AWS, Azure, GCP).

## Enter the final URL

Every request is egress-checked and **redirects are refused, not followed**. Enter the final `https://` URL the server answers on:

- A self-hosted Jenkins, GitLab or Jira behind an `http` to `https` redirect, or a login or context-path redirect, now fails instead of being followed. Use the URL after the redirect.
- GitHub answers a renamed or transferred repository with a `301`; it surfaces as a non-200 result. Use the repository's current name.

## Who may reach which address

| Integration | Allowed targets |
|---|---|
| Jenkins, GitLab, CircleCI Server, GitHub Enterprise, Jira (admin-configured) | Public addresses; RFC-1918 addresses only when `AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS=true`. Loopback and link-local (cloud metadata) are never allowed. |
| Jira configured per company (Company OS `pm-config`) | Public addresses only, whatever the flag says: the URL is tenant-editable. |
| Bitbucket (Cloud API only), Slack, Discord, Teams, Trello, Asana, Notion, Microsoft 365, Datadog, New Relic, AWS, Azure, GCP | Public addresses only. |
