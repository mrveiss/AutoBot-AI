# Enterprise Knowledge Base Connectors — Operator Setup Guide

> Issue #10538 — Slack, Confluence and Jira ingestion connectors for the AutoBot
> knowledge base.

This guide is for operators wiring the enterprise Knowledge Base (KB) connectors
that ingest **Slack** channel/thread history, **Confluence** wiki pages and
**Jira** issues (with comments) into the KB so they become searchable via
`kb.search`.

All connector types, config fields and API endpoints below are cited to the
exact source lines they are read from. No credentials are invented, and the
config keys documented here are the ones the connectors actually read — see
[Auth-field alignment](#auth-field-alignment) for how that is kept true.

## Important: disabled by default in production

These three connectors reach third-party SaaS APIs and ship **disabled by
default**. They are registered with `ConnectorRegistry` only when the
`kb_enterprise_connectors` feature flag is enabled
(`autobot-backend/knowledge/connectors/__init__.py:85-88`). Until the flag is
on, `ConnectorRegistry.get_registered_class()` returns `None` for these types
and `POST /api/knowledge_base/connectors` returns **422**
(`autobot-backend/api/knowledge_connectors.py:81-87`, `:409-414`).

All KB connector endpoints require admin permission
(`autobot-backend/api/knowledge_connectors.py:66-69`).

## Step 1 — Enable the feature flag

Set the environment variable on every backend node that must serve these
connectors, then restart the backend:

```bash
export AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true
```

The flag name and default are defined in
`autobot_shared/feature_flags.py:25-26` (mapped at `:61`); it defaults to
`False` (opt-in). Feature env vars follow the `AUTOBOT_FEATURE_<NAME>` pattern
(`autobot_shared/feature_flags.py:12`, `:74`).

For **offline testing** of the shared sync pipeline without any live
credentials, a credential-free `mock` connector is available behind a separate
flag (`autobot_shared/feature_flags.py:27-28`):

```bash
export AUTOBOT_FEATURE_KB_MOCK_CONNECTOR=true
```

The `mock` connector replays local JSON fixtures with zero network access and
exercises the exact same `sync()` pipeline the enterprise connectors use
(`autobot-backend/knowledge/connectors/mock.py:5-31`). Do **not** enable the
mock flag in production — the gate exists purely to keep `mock` out of the
production connector-type listing (`mock.py:24-30`).

## Step 2 — Obtain credentials

### Slack

The Slack connector calls the Slack Web API with a bearer bot token
(`autobot-backend/knowledge/connectors/slack.py:257-263`).

- Create a Slack app and a **bot token** (`xoxb-...`) with the
  `channels:history`, `groups:history` and `channels:read` scopes
  (`slack.py:20-22`).
- Collect the **channel IDs** you want ingested (`slack.py:26`).
- The token is verified via `auth.test`; history is read via
  `conversations.history` / `conversations.replies`
  (`slack.py:114`, `:226`, `:247`).

### Confluence (Atlassian Cloud)

The Confluence connector uses HTTP Basic auth (account email + API token)
against the Confluence REST API (`confluence.py:67-70`, `:223-242`).

- Create an **Atlassian API token** at your Atlassian account security page.
- Note your Atlassian **account email** (used as the Basic-auth login).
- Determine the site **base URL including `/wiki`**, e.g.
  `https://your-domain.atlassian.net/wiki` (`confluence.py:18-19`).
- Collect the **space keys** to sync (`confluence.py:27`).

### Jira (Atlassian Cloud)

The Jira connector uses the same Atlassian API-token + email Basic auth against
the Jira REST API v3 (`jira.py:73-76`, `:238-257`).

- Reuse (or create) an **Atlassian API token**.
- Note your Atlassian **account email**.
- Determine the site **base URL without `/wiki`**, e.g.
  `https://your-domain.atlassian.net` (`jira.py:18-19`).
- Collect the **project keys** to sync (`jira.py:27`), or supply an explicit
  `jql` override (`jira.py:28-29`).

## Step 3 — Connector config fields

Each connector reads its settings from the `config` object of the create
request (`ConnectorConfig.config`). The tables below list the **exact keys each
connector's `__init__` reads**, with defaults, cited to source.

### Slack config keys

| Key | Required | Default | Source |
|---|---|---|---|
| `token` | yes | `""` | `slack.py:101` |
| `channel_ids` | yes | `[]` | `slack.py:102` |
| `sync_threads` | no | `True` | `slack.py:103` |
| `oldest` | no | `"0"` | `slack.py:104` |
| `page_size` | no | `200` | `slack.py:105` |
| `slack_api_base` | no (testing) | `https://slack.com/api` | `slack.py:106` |

`token` is the canonical `BearerAuth` field (`connector_auth.py:18-23`) — see
[Auth-field alignment](#auth-field-alignment).

### Confluence config keys

| Key | Required | Default | Source |
|---|---|---|---|
| `base_url` | yes | `""` | `confluence.py:92` |
| `username` | yes | `""` | `confluence.py:90` |
| `password` | yes | `""` | `confluence.py:91` |
| `space_keys` | yes | `[]` | `confluence.py:93` |
| `page_size` | no | `25` | `confluence.py:94` |

`username`/`password` are the canonical `BasicAuth` fields
(`connector_auth.py:37-43`) — `username` holds the Atlassian account email and
`password` holds the API token.

### Jira config keys

| Key | Required | Default | Source |
|---|---|---|---|
| `base_url` | yes | `""` | `jira.py:100` |
| `username` | yes | `""` | `jira.py:98` |
| `password` | yes | `""` | `jira.py:99` |
| `project_keys` | yes | `[]` | `jira.py:101` |
| `jql` | no (overrides project keys) | `""` | `jira.py:102` |
| `page_size` | no | `50` | `jira.py:103` |

Same `BasicAuth` mapping as Confluence: `username` = Atlassian account email,
`password` = API token.

## Step 4 — Register a connector and run the first sync

Connectors are created through the admin KB API. The request body schema is
`CreateConnectorRequest`
(`autobot-backend/knowledge/schemas/connectors.py:206-222`): `connector_type`,
`name`, `config`, plus optional `enabled`, `verification_mode`,
`schedule_cron`, `include_patterns`, `exclude_patterns`, `max_concurrency`,
`secret_id`.

### 4a — Verify the type is registered

```bash
curl -s -X GET https://<backend-host>/api/knowledge_base/connector_types
```

With the flag on, `slack`, `confluence` and `jira` appear in the list
(`autobot-backend/api/knowledge_connectors.py:346-369`). If they are absent,
the flag is not active on that node.

### 4b — Create the connector

`POST /api/knowledge_base/connectors` validates the type, validates the config
against the connector's declared auth schema, runs `test_connection()`, and
only persists on success (`knowledge_connectors.py:395-482`). A failed
connection test returns **400** and the connector is not saved
(`knowledge_connectors.py:467-478`).

Slack example:

```bash
curl -s -X POST https://<backend-host>/api/knowledge_base/connectors \
  -H 'Content-Type: application/json' \
  -d '{
        "connector_type": "slack",
        "name": "Engineering Slack",
        "config": {
          "token": "<SLACK_BOT_TOKEN>",
          "channel_ids": ["C0123456789"]
        }
      }'
```

Confluence example:

```bash
curl -s -X POST https://<backend-host>/api/knowledge_base/connectors \
  -H 'Content-Type: application/json' \
  -d '{
        "connector_type": "confluence",
        "name": "Team Wiki",
        "config": {
          "base_url": "https://your-domain.atlassian.net/wiki",
          "username": "<ATLASSIAN_EMAIL>",
          "password": "<ATLASSIAN_API_TOKEN>",
          "space_keys": ["ENG", "OPS"]
        }
      }'
```

Jira example:

```bash
curl -s -X POST https://<backend-host>/api/knowledge_base/connectors \
  -H 'Content-Type: application/json' \
  -d '{
        "connector_type": "jira",
        "name": "Delivery Tracker",
        "config": {
          "base_url": "https://your-domain.atlassian.net",
          "username": "<ATLASSIAN_EMAIL>",
          "password": "<ATLASSIAN_API_TOKEN>",
          "project_keys": ["ABC", "XYZ"]
        }
      }'
```

The response returns a generated `connector_id`
(`knowledge_connectors.py:408`, `:482`). Save it for the next steps.

### 4c — Trigger the first sync

Sync runs as a background task (`knowledge_connectors.py:666-687`).
`incremental` defaults to `true` (`knowledge_connectors.py:675`); for the first
full ingest pass `incremental=false`:

```bash
curl -s -X POST \
  "https://<backend-host>/api/knowledge_base/connectors/<connector_id>/sync?incremental=false"
```

A `mock` connector is handy to prove the pipeline first (with
`AUTOBOT_FEATURE_KB_MOCK_CONNECTOR=true`), since `MockConnector` does not
override `sync()` and runs the identical inherited pipeline offline
(`mock.py:5-16`).

### 4d — Verify ingestion

- **Re-test the connection** on demand:

  ```bash
  curl -s -X POST https://<backend-host>/api/knowledge_base/connectors/<connector_id>/test
  ```

  Returns `{ "healthy": true|false }` (`knowledge_connectors.py:642-663`).

- **In-flight job state** (`knowledge_connectors.py:720-762`, 404 when no job is
  active):

  ```bash
  curl -s -X GET https://<backend-host>/api/knowledge_base/connectors/<connector_id>/job
  ```

- **Sync history** — status, added/updated/deleted counts, errors, duration
  (`knowledge_connectors.py:690-717`):

  ```bash
  curl -s -X GET "https://<backend-host>/api/knowledge_base/connectors/<connector_id>/history?limit=20"
  ```

- **Aggregate health** across all live connectors
  (`knowledge_connectors.py:510-527`):

  ```bash
  curl -s -X GET https://<backend-host>/api/knowledge_base/connectors/health
  ```

Change-detection checkpoints are stored in Redis (knowledge DB) via the shared
`_load_ts()` / `_store_ts()` helpers on `AbstractConnector`
(`base.py:272-291`, `:293-308` — extracted from six byte-identical
per-connector copies in #12659). The default key prefix is
`connector:<connector_type>:ts:` (`base.py:268-269`) — i.e.
`connector:slack:ts:`, `connector:confluence:ts:`, `connector:jira:ts:` — each
with a 30-day TTL (`base.py:52`).

## Auth-field alignment

The credential-handling layer and the connector bodies read the **same**
config keys, so the examples above are the correct, currently-working request
shape:

- The create endpoint validates the request `config` against the connector's
  declared `auth_schema()` and requires those schema fields to be present
  (`knowledge_connectors.py:423`, validation logic
  `autobot_shared/auth/connector_auth.py:68-84`). It then extracts the
  schema's sensitive fields into the encrypted credential store and strips them
  from the stored config (`credential_store.py:82-84`).
- Slack declares `BearerAuth`, whose sensitive/required field is `token`
  (`slack.py:78-81`; `connector_auth.py:18-23`) — `SlackConnector.__init__`
  reads the same `token` key (`slack.py:101`).
- Confluence and Jira declare `BasicAuth`, whose fields are `username` and
  `password` (`confluence.py:67-70`, `jira.py:73-76`;
  `connector_auth.py:37-43`) — their `__init__` methods read the same
  `username`/`password` keys (`confluence.py:90-91`, `jira.py:98-99`).

This alignment was fixed in #12225 (tracked from #12221), which renamed the
per-connector reads to match the declared schema; prior to that fix, a request
that satisfied the connector docstrings (`bot_token` / `email` + `api_token`)
would not have satisfied auth-schema validation. That mismatch no longer
exists in the current code.

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| `422` on create, type "not registered" | `kb_enterprise_connectors` flag off on that node | `knowledge_connectors.py:81-87`, `:409-414` |
| `422` "Auth config invalid" | Missing auth-schema field (`token` / `username` + `password`) | `knowledge_connectors.py:423`; `connector_auth.py:68-84` |
| `400` "Connection test failed" | Bad/expired token, wrong `base_url`, no channel/space/project access | `test_connection` per connector (`slack.py:112-118`, `confluence.py:100-106`, `jira.py:109-115`) |
| Empty sync (no facts) | Wrong `channel_ids` / `space_keys` / `project_keys`, or `oldest`/`jql` filters out everything | `slack.py:120-127`, `confluence.py:108-115`, `jira.py:117-120` |
| Sync slows / stalls under load | Upstream `HTTP 429` rate limiting is retried as `RetryableError` | `slack.py:274-275`, `confluence.py:232-233`, `jira.py:247-248` |
| Upstream `5xx` errors | Retried as `RetryableError`; `4xx` (non-429) are logged and skipped | `slack.py:276-277`, `confluence.py:234-235`, `jira.py:249-250` |
| Confluence `404`/empty on valid space | `base_url` missing the `/wiki` suffix | `confluence.py:18-19` |
| Jira returns nothing for known project | `base_url` wrongly includes `/wiki`, or `jql` override shadows `project_keys` | `jira.py:18-19`, `:176-184` |

## Reference

- Connector category map and type table:
  `autobot-backend/knowledge/connectors/CONNECTORS.md`
- Connector framework overview:
  `autobot-backend/knowledge/connectors/__init__.py`
- Feature flags: `autobot_shared/feature_flags.py`
- KB connector API: `autobot-backend/api/knowledge_connectors.py`
</content>
