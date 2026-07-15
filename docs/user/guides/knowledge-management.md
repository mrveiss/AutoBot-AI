# Knowledge Management Guide

The Knowledge Base is where AutoBot stores and organizes your documents, notes,
and data. This guide explains every section of the Knowledge Base and how to
use it effectively.

## Accessing the Knowledge Base

Click **Knowledge Base** in the navigation bar, or navigate to `/knowledge`.
A sidebar on the left lists all available sections.

<!-- Screenshot: Knowledge Base view with sidebar sections -->

## Sections Overview

| Section | Path | Purpose |
|---------|------|---------|
| Search | `/knowledge/browser` | Find information across all documents |
| Research | `/knowledge/research` | Live research panel with browser collaboration |
| Categories | `/knowledge/browser` | Browse documents organized by topic |
| Knowledge Graph | `/knowledge/graph` | Visual map of topics and relationships |
| Manage | `/knowledge/manage` | Add, edit, and delete knowledge entries |
| Verification | `/knowledge/health?tab=verification` | Review and approve imported content |
| Connectors | `/knowledge/connectors` | Import data from external sources |
| Statistics | `/knowledge/health` | View usage metrics and storage details (Analytics tab) |
| Maintenance | `/knowledge/health?tab=tools` | Clean up, re-index, and maintain data |

## Uploading Documents

1. Navigate to **Manage** (`/knowledge/manage`).
2. Click the **Upload** or **Add Entry** button.
3. Select a file from your computer. Common formats include PDF, TXT, Markdown,
   CSV, and DOCX.
4. Optionally add:
   - **Title** -- a human-readable name for the document.
   - **Category** -- a topic grouping (for example, "Finance" or "HR Policies").
   - **Tags** -- keywords to make searching easier.
5. Click **Save** to upload. Processing happens in the background.

<!-- Screenshot: Upload form with title, category, and tags -->

## Searching Knowledge

1. Go to the **Browser** (`/knowledge/browser`).
2. Type a keyword, phrase, or full question in the search bar.
3. Press **Enter**.
4. Results appear ranked by relevance, showing matching passages and the
   document they came from.

Search also works from the chat: ask AutoBot a question and it will
automatically search the knowledge base if relevant documents exist.

## Browsing Categories

1. Go to the **Browser** (`/knowledge/browser`).
2. Categories are displayed as folders or cards.
3. Click a category to see all documents within it.
4. Click a document to read its content or edit its metadata.

## Knowledge Graph

The Knowledge Graph (`/knowledge/graph`) is an interactive visualization that
shows how your documents, topics, and entities relate to each other.

- **Nodes** represent documents, topics, or entities.
- **Edges** (lines) represent relationships.
- Click a node to see its details.
- Zoom in and out to explore large graphs.

Sub-sections within the Knowledge Graph:

| Sub-section | Path | Purpose |
|-------------|------|---------|
| Pipeline | `/knowledge/graph/pipeline` | Run processing pipelines on your data |
| Entities | `/knowledge/graph/entities` | Explore extracted entities |
| Timeline | `/knowledge/graph/timeline` | View events on a chronological timeline |
| Summaries | `/knowledge/graph/summaries` | Search and browse auto-generated summaries |

<!-- Screenshot: Knowledge Graph visualization -->

## Source Verification

The Verification Queue (`/knowledge/health?tab=verification`) lets you review content
before it is used in AI responses:

1. Open the queue to see pending items.
2. Review each item for accuracy.
3. **Approve** to make the content available, or **Reject** to remove it.

This is especially useful when importing content from external sources.

## Connectors

Connectors (`/knowledge/connectors`) pull data from external services
automatically. To set up a connector:

1. Go to **Connectors**.
2. Click **Add Connector**.
3. Choose the source type and provide any required credentials or URLs.
4. Configure the sync schedule (how often data is refreshed).
5. Save the connector. Data will begin importing on the configured schedule.

## Statistics and Maintenance

- **Statistics** — the Analytics tab of the Health view (`/knowledge/health`)
  shows how many documents you have, storage used, and search activity.
- **Maintenance** — the Tools tab of the Health view
  (`/knowledge/health?tab=tools`) provides tools to re-index documents, clean
  up orphaned entries, and optimize storage.

## Tips

- Add meaningful titles and tags when uploading. This dramatically improves
  search quality.
- Use the verification queue to ensure imported content is accurate before the
  AI uses it.
- Check the Knowledge Graph periodically to discover unexpected connections
  between your documents.

## Related Guides

- [Quick Start: Knowledge Base](../quick-start-knowledge.md)
- [Chat Interface](chat-interface.md) -- asking questions about your knowledge
- [Working with Agents](working-with-agents.md) -- agents can search and manage
  knowledge on your behalf
