# GitLab / Gitea / Forgejo Connectors

## Overview

AutoBot supports three self-hosted git platform connectors for indexing repositories, issues, merge/pull requests, and documentation into the knowledge base:

- **GitLab** — GitLab REST API v4 (gitlab.com or self-hosted)
- **Gitea** — Gitea REST API v1 (self-hosted)
- **Forgejo** — Forgejo REST API v1 (compatible with Gitea)

## Features

All three connectors support:
- ✅ **Issue indexing** — Index all issues with title, description, labels, state, and metadata
- ✅ **Merge/Pull request indexing** — Index MRs/PRs with full context
- ✅ **Repository file indexing** — Optional indexing of README files and source code
- ✅ **Incremental sync** — Only fetch changed items since last sync
- ✅ **Change detection** — Detect additions, modifications, and deletions
- ✅ **Scheduled sync** — Configure cron schedules for automatic updates
- ✅ **Credential management** — Secure token storage via credential store

## Configuration

### GitLab Connector

```json
{
  "connector_type": "gitlab",
  "name": "My GitLab Instance",
  "config": {
    "token": "glpat-xxxx",
    "gitlab_url": "https://gitlab.example.com",
    "project_ids": ["42", "123"],
    "sync_issues": true,
    "sync_merge_requests": true,
    "sync_files": false,
    "per_page": 100,
    "max_concurrency": 4
  },
  "enabled": true,
  "schedule_cron": "0 */4 * * *"
}
```

**Config keys:**
- `token` (required) — Personal access token with `read_api` scope
- `gitlab_url` — Base URL (default: `https://gitlab.com`)
- `project_ids` — List of project IDs to sync (empty = all accessible projects)
- `sync_issues` — Index issues (default: `true`)
- `sync_merge_requests` — Index merge requests (default: `true`)
- `sync_files` — Index README and source files (default: `false`)
- `per_page` — Page size for pagination (default: `100`)
- `max_concurrency` — Parallel source fetches (default: `4`)

### Gitea / Forgejo Connector

```json
{
  "connector_type": "gitea",
  "name": "My Gitea Instance",
  "config": {
    "token": "xxxx",
    "gitea_url": "https://gitea.example.com",
    "repos": ["owner/repo1", "owner/repo2"],
    "sync_issues": true,
    "sync_merge_requests": true,
    "sync_files": false,
    "per_page": 50,
    "max_concurrency": 4
  },
  "enabled": true,
  "schedule_cron": "0 */6 * * *"
}
```

**Config keys:**
- `token` (required) — Personal access token
- `gitea_url` (required) — Base URL of Gitea/Forgejo instance
- `repos` (required) — List of repositories in `owner/repo` format
- `sync_issues` — Index issues (default: `true`)
- `sync_merge_requests` — Index pull requests (default: `true`)
- `sync_files` — Index README and source files (default: `false`)
- `per_page` — Page size for pagination (default: `50`)
- `max_concurrency` — Parallel source fetches (default: `4`)

**Note:** For Forgejo, use `"connector_type": "forgejo"` — the API is identical to Gitea.

## API Usage

### Create a Connector

```bash
curl -X POST http://localhost:8001/api/knowledge_base/connectors \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "connector_type": "gitlab",
    "name": "GitLab Production",
    "config": {
      "token": "glpat-xxxx",
      "gitlab_url": "https://gitlab.example.com",
      "project_ids": ["42"],
      "sync_issues": true,
      "sync_merge_requests": true,
      "sync_files": false
    },
    "enabled": true,
    "schedule_cron": "0 */4 * * *"
  }'
```

### Test Connection

```bash
curl -X POST http://localhost:8001/api/knowledge_base/connectors/{connector_id}/test \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Trigger Sync

```bash
# Full sync
curl -X POST http://localhost:8001/api/knowledge_base/connectors/{connector_id}/sync \
  -H "Authorization: Bearer YOUR_TOKEN"

# Incremental sync
curl -X POST http://localhost:8001/api/knowledge_base/connectors/{connector_id}/sync?incremental=true \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### View Sync History

```bash
curl http://localhost:8001/api/knowledge_base/connectors/{connector_id}/history \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## File Indexing

When `sync_files: true`, the connector indexes text files from repositories:

**Supported file types:**
- Markdown: `.md`, `.rst`
- Programming: `.py`, `.js`, `.ts`, `.go`, `.rb`, `.java`, `.c`, `.cpp`, `.rs`, etc.
- Config: `.yaml`, `.yml`, `.json`, `.toml`, `.ini`, `.cfg`, `.conf`
- Documentation: `.txt`, `.html`, `.xml`
- Scripts: `.sh`, `.bash`

Binary files (images, archives, executables) are skipped.

## Incremental Sync

All connectors support incremental sync via `updated_at` timestamps:

1. First sync indexes all items
2. Subsequent syncs only fetch items updated since last sync
3. Timestamps cached in Redis per source
4. Change detection compares cached vs API timestamps

## Source ID Format

Each indexed item gets a unique source ID:

**GitLab:**
- Issues: `gitlab:{connector_id}:project:{project_id}:issue:{iid}`
- MRs: `gitlab:{connector_id}:project:{project_id}:mr:{iid}`
- Files: `gitlab:{connector_id}:project:{project_id}:file:{path}`

**Gitea/Forgejo:**
- Issues: `gitea:{connector_id}:repo:{owner}:{repo}:issue:{number}`
- PRs: `gitea:{connector_id}:repo:{owner}:{repo}:pr:{number}`
- Files: `gitea:{connector_id}:repo:{owner}:{repo}:file:{path}`

## Metadata

Each indexed item includes structured metadata for filtering and search:

**GitLab:**
```json
{
  "gitlab_project_id": "42",
  "gitlab_issue_iid": "123",
  "gitlab_issue_url": "https://gitlab.example.com/project/-/issues/123",
  "title": "Issue title",
  "state": "opened",
  "updated_at": "2026-06-04T12:00:00Z",
  "connector_type": "gitlab"
}
```

**Gitea/Forgejo:**
```json
{
  "gitea_owner": "alice",
  "gitea_repo": "my-repo",
  "issue_number": "42",
  "issue_url": "https://gitea.example.com/alice/my-repo/issues/42",
  "title": "Issue title",
  "state": "open",
  "updated_at": "2026-06-04T12:00:00Z",
  "connector_type": "gitea"
}
```

## Authentication

### GitLab

Create a personal access token with `read_api` scope:
1. Go to User Settings → Access Tokens
2. Create token with `read_api` scope
3. Copy token and add to connector config

### Gitea/Forgejo

Create a personal access token:
1. Go to Settings → Applications → Generate New Token
2. Select appropriate scopes (read:repository, read:issue)
3. Copy token and add to connector config

## Rate Limiting

All connectors implement automatic retry with exponential backoff for rate-limited requests:
- HTTP 429 responses trigger 5-second initial delay
- Subsequent retries double the delay (5s → 10s → 20s)
- Maximum 3 retries before failing

## Error Handling

Common errors and solutions:

**401 Unauthorized:**
- Check token is valid and not expired
- Verify token has required scopes

**403 Forbidden:**
- Token lacks access to specified projects/repos
- Check project visibility settings

**404 Not Found:**
- Project ID or repo path incorrect
- Verify instance URL is correct

**Rate Limited (429):**
- Connector will auto-retry with backoff
- Consider reducing `per_page` or `max_concurrency`

## Performance Tuning

**Large instances:**
- Set `sync_files: false` to skip repository file indexing
- Reduce `max_concurrency` to avoid rate limits
- Increase `per_page` (up to 100) for fewer API calls
- Use incremental sync via scheduled jobs

**Small instances:**
- Enable `sync_files: true` for comprehensive indexing
- Increase `max_concurrency` (up to 8) for faster sync
- Schedule more frequent syncs (hourly vs daily)

## Implementation

Connector implementation: `autobot-backend/knowledge/connectors/gitlab.py`
- `GitLabConnector` — GitLab API v4
- `GiteaConnector` — Gitea/Forgejo API v1

Both inherit from `AbstractConnector` and implement:
- `test_connection()` — Verify credentials
- `discover_sources()` — List all indexable items
- `fetch_content()` — Retrieve content for a source
- `detect_changes()` — Identify modified items since last sync

## Related

- [Connector API Reference](../api/connectors.md)
- [Knowledge Base Architecture](../architecture/knowledge-base.md)
- [Credential Store](../security/credential-store.md)
