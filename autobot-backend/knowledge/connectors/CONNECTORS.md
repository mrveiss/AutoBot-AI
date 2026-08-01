# Connector Category Reference

Issue #10539 — tool-agnostic connector category abstraction.

Skills and workflow steps can resolve connectors by **category** instead of by
a hard-coded vendor type.  `ConnectorRegistry.resolve_by_category(category)`
returns every **live** (configured + started) instance whose `connector_type`
belongs to that category.  The lookup is case-insensitive.

## Category Map

| Category | Connector types |
|---|---|
| `cloud storage` | `gdrive`, `onedrive`, `nextcloud` |
| `source control` | `gitlab`, `gitea` |
| `wiki` | `notion`, `confluence` |
| `knowledge base` | `notion`, `file_server`, `web_crawler`, `confluence` |
| `file system` | `file_server` |
| `database` | `database` |
| `web` | `web_crawler` |
| `audio` | `audio` |
| `external` | `external_adapter` |
| `chat` | `slack` |
| `issue tracker` | `jira` |

## Connector Types

| Type | File | Description |
|---|---|---|
| `gdrive` | `gdrive.py` | Google Drive API v3 |
| `onedrive` | `onedrive.py` | Microsoft OneDrive / SharePoint |
| `nextcloud` | `nextcloud.py` | Nextcloud WebDAV |
| `gitlab` | `gitlab.py` | GitLab REST API v4 |
| `gitea` | `gitlab.py` | Gitea / Forgejo REST API v1 |
| `notion` | `notion.py` | Notion databases and pages |
| `file_server` | `file_server.py` | Local / NFS / SMB mounts |
| `web_crawler` | `web_crawler.py` | Playwright-based web crawler |
| `database` | `database.py` | SQLAlchemy-backed databases |
| `audio` | `audio_connector.py` | Audio file ingestion |
| `external_adapter` | `external_adapter.py` | Subprocess / stdout-JSON adapters |
| `slack` | `slack.py` | Slack Web API channel/thread history — Issue #10538, feature-flagged (`AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS`, default off) |
| `confluence` | `confluence.py` | Atlassian Confluence REST API pages — Issue #10538, feature-flagged (`AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS`, default off) |
| `jira` | `jira.py` | Atlassian Jira REST API v3 issues + comments — Issue #10538, feature-flagged (`AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS`, default off) |

## Usage

```python
from knowledge.connectors import ConnectorRegistry, CATEGORY_MAP

# Resolve all configured "cloud storage" connectors:
instances = ConnectorRegistry.resolve_by_category("cloud storage")

# Inspect the full map:
print(CATEGORY_MAP)
```

Workflow steps carry the intended category in their `inputs` dict:

```python
WorkflowStep(
    task_id="kb_search",
    agent_type="librarian",
    action="Search existing knowledge base for relevant information",
    inputs={"connector_category": "knowledge base"},
)
```

The agent reads `inputs["connector_category"]` and calls
`ConnectorRegistry.resolve_by_category(...)` to obtain live connectors without
knowing which vendor is deployed.
