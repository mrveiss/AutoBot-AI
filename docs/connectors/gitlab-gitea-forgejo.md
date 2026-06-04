---
tags: [type/reference, status/current, component/backend]
date: 2026-06-04
---

# GitLab / Gitea / Forgejo Connectors

AutoBot supports three self-hosted git platform connectors for indexing repositories, issues, merge/pull requests, and documentation into the knowledge base.

| Connector | API | Notes |
|---|---|---|
| GitLab | REST API v4 | gitlab.com or self-hosted |
| Gitea | REST API v1 | self-hosted |
| Forgejo | REST API v1 | Gitea-compatible |

---

## Shared Feature Set

All three connectors support:

- **Issue indexing** — title, description, labels, state, metadata
- **Merge/Pull request indexing** — full context
- **Repository file indexing** — optional; README files and source code
- **Incremental sync** — only changed items since last sync
- **Change detection** — additions, modifications, deletions
- **Scheduled sync** — configurable cron schedule
- **Credential management** — secure token storage via credential store

---

## Configuration

### GitLab

```json
{
  "connector_type": "gitlab",
  "name": "My GitLab Instance",
  "config": {
    "url": "https://gitlab.example.com",
    "token": "glpat-xxxxxxxxxxxxxxxxxxxx",
    "projects": ["group/repo1", "group/repo2"],
    "sync_schedule": "0 */6 * * *"
  }
}
```

### Gitea

```json
{
  "connector_type": "gitea",
  "name": "My Gitea Instance",
  "config": {
    "url": "https://gitea.example.com",
    "token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "repos": ["owner/repo1"],
    "sync_schedule": "0 */6 * * *"
  }
}
```

### Forgejo

Same schema as Gitea with `"connector_type": "forgejo"`.

---

## Incremental Sync

Each connector stores a `last_sync` timestamp in Redis. On subsequent runs it fetches only items updated since that timestamp, using `updated_after` query parameters in the upstream API.

---

## Credential Storage

Tokens are stored via the AutoBot credential store (not in plain config files). Use the Settings UI or the credentials API to add tokens before enabling a connector.
