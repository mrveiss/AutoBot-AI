# Knowledge System Vision — Gap Analysis & Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bridge the gap between AutoBot's current Knowledge system and the full vision — grounded RAG with live research agents, source verification workflows, unlimited live connectors, and observable browser collaboration.

**Architecture:** Extend the existing 13-mixin KB architecture with a pluggable Connector Framework for external sources (file servers, databases, web crawlers), add a Source Verification workflow with autonomous/collaborative modes, and integrate the browser observation panel into the Knowledge page for live research visibility.

**Tech Stack:** Python 3.12 (FastAPI), Vue 3 + TypeScript, ChromaDB, Redis, Playwright (.25), existing KnowledgeBase mixins, existing LibrarianAssistant agent.

---

## Current State vs Vision

### What Exists (Production-Ready)

| Component | Status | Key Files |
|-----------|--------|-----------|
| Core RAG pipeline (ChromaDB + hybrid search + reranking) | Complete | `knowledge/` (13 mixins), `services/rag_service.py` |
| Document ingestion (files, URLs, text) | Complete | `knowledge/documents.py`, `knowledge/facts.py` |
| Librarian Agent (KB search) | Complete | `agents/kb_librarian/librarian.py` |
| Librarian Assistant (web research via Playwright) | Complete | `agents/librarian_assistant.py` |
| Knowledge Graph + entity visualization | Complete | `knowledge/pipeline/`, frontend `graph/` components |
| Ownership, collaboration, access control | Complete | `api/knowledge_ownership.py`, `api/knowledge_collaboration.py` |
| Audit logging | Complete | `api/knowledge_audit.py`, `knowledge/audit_log.py` |
| Frontend (56 components, 7 sections) | Complete | `components/knowledge/` |
| KnowledgeSyncService (15-min doc sync) | Complete | `services/knowledge_sync_service.py` |
| ECL Pipeline framework (Extract, Cognify, Load) | Partial | `knowledge/pipeline/` — extractors done, cognifiers stubbed |

### What's Missing (Gaps)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 1 | **Source Connector Framework** — No pluggable connectors for file servers (SMB/NFS/S3), databases (PostgreSQL, MySQL, MongoDB), web crawlers, RSS feeds | High — users can only manually upload or use Librarian Assistant | Large |
| 2 | **Source Verification/Approval Workflow** — Librarian Assistant auto-stores if quality > 0.7; no user approval gate, no collaborative mode, no approval UI | High — trust gap, users can't control what enters KB | Medium |
| 3 | **Observable Research in Knowledge Page** — Browser panel exists in chat (`VisualBrowserPanel.vue`) but Knowledge page has no live research observation | Medium — users must switch to chat to watch research | Medium |
| 4 | **Source Provenance Tracking** — Metadata has `stored_by` and `quality_score` but no `approved_by`, `approval_timestamp`, `verification_method` (auto/manual), `source_connector_id` | Medium — no auditability on how sources entered KB | Small |
| 5 | **Connector Scheduling & Sync Management** — KnowledgeSyncService syncs internal docs but has no concept of external connector schedules, incremental change detection for live sources | Medium — connectors would re-process everything | Medium |
| 6 | **Pipeline Cognifiers** — Entity/event/relationship extraction models defined but implementations are stubs | Low — enrichment layer, not blocking core use | Medium |

---

## Implementation Phases

### Phase 1: Source Provenance & Verification Foundation (Backend)

**Why first:** This is the trust layer. Before adding more source types, we need the ability to track where knowledge comes from and who approved it.

#### 1A. Source Provenance Metadata

Extend the existing knowledge metadata schema to track source origin and approval status.

**Files:**
- Modify: `autobot-backend/knowledge/facts.py` — add provenance fields to fact storage
- Modify: `autobot-backend/knowledge/documents.py` — add provenance fields to document storage
- Modify: `autobot-backend/api/knowledge_models.py` — add provenance Pydantic models
- Modify: `autobot-backend/agents/librarian_assistant.py:340-367` — enrich metadata with provenance

**Provenance fields to add:**
```python
# Added to document/fact metadata
{
    "source_type": "manual_upload|url_fetch|web_research|connector",
    "source_connector_id": None,  # filled by connectors
    "verification_status": "unverified|pending_review|verified|rejected",
    "verification_method": "auto_quality|user_approved|connector_trusted",
    "verified_by": None,  # user ID when manually verified
    "verified_at": None,  # timestamp
    "quality_score": 0.0,  # from LLM assessment
    "provenance_chain": [],  # list of {action, actor, timestamp}
}
```

#### 1B. Source Verification Workflow API

Add endpoints for reviewing and approving/rejecting pending sources.

**Files:**
- Create: `autobot-backend/api/knowledge_verification.py` — verification endpoints
- Modify: `autobot-backend/main.py` — register new router

**Endpoints:**
- `GET /api/knowledge/verification/pending` — list sources pending review
- `POST /api/knowledge/verification/{fact_id}/approve` — approve a source
- `POST /api/knowledge/verification/{fact_id}/reject` — reject (remove from KB)
- `PUT /api/knowledge/verification/config` — set verification mode (autonomous/collaborative)
- `GET /api/knowledge/verification/config` — get current verification config

#### 1C. Librarian Assistant Verification Mode

Modify LibrarianAssistant to support collaborative mode (present to user, wait for approval) vs autonomous mode (current behavior with auto-store).

**Files:**
- Modify: `autobot-backend/agents/librarian_assistant.py` — add verification mode support
- Modify: `autobot-backend/config/config.yaml` — add verification config section

**Behavior change:**
- `autonomous` mode (current): auto-store if quality > threshold, mark as `verification_method: auto_quality`
- `collaborative` mode (new): store with `verification_status: pending_review`, emit WebSocket event to frontend, wait for user action
- Configurable per-source-type and globally

---

### Phase 2: Source Verification Frontend

#### 2A. Verification Queue UI

Add a verification section to the Knowledge page where pending sources appear for review.

**Files:**
- Create: `autobot-frontend/src/components/knowledge/KnowledgeVerificationQueue.vue` — pending sources list with approve/reject actions
- Modify: `autobot-frontend/src/views/KnowledgeView.vue` — add Verification nav item
- Modify: `autobot-frontend/src/router/index.ts` — add `/knowledge/verification` route
- Modify: `autobot-frontend/src/stores/useKnowledgeStore.ts` — add verification state
- Modify: `autobot-frontend/src/models/repositories/KnowledgeRepository.ts` — add verification API calls
- Modify: `autobot-frontend/src/types/knowledgeBase.ts` — add verification types

**UI features:**
- List of pending sources with preview (title, domain, quality score, content snippet)
- Approve/Reject buttons per item
- Bulk approve/reject
- Source preview panel (reuse existing `SourcePreviewPanel.vue`)
- Verification mode toggle (autonomous/collaborative)
- Filter by source type

#### 2B. Provenance Display

Show provenance information on existing knowledge entries.

**Files:**
- Modify: `autobot-frontend/src/components/knowledge/KnowledgeEntries.vue` — add provenance badge/column
- Modify: `autobot-frontend/src/components/knowledge/KnowledgeContentViewer.vue` — show provenance trail
- Modify: `autobot-frontend/src/types/knowledgeBase.ts` — add provenance types

---

### Phase 3: Source Connector Framework (Backend)

**Why:** This is the largest piece — the pluggable architecture for external data sources.

#### 3A. Connector Base Architecture

Create the abstract connector interface and registry.

**Files:**
- Create: `autobot-backend/knowledge/connectors/__init__.py`
- Create: `autobot-backend/knowledge/connectors/base.py` — AbstractConnector base class
- Create: `autobot-backend/knowledge/connectors/registry.py` — ConnectorRegistry (discover, register, manage)
- Create: `autobot-backend/knowledge/connectors/models.py` — ConnectorConfig, ConnectorStatus, SyncResult models

**AbstractConnector interface:**
```python
class AbstractConnector(ABC):
    connector_type: str  # "file_server", "database", "web_crawler", "rss"

    @abstractmethod
    async def test_connection(self) -> bool: ...

    @abstractmethod
    async def discover_sources(self) -> List[SourceInfo]: ...

    @abstractmethod
    async def fetch_content(self, source_id: str) -> ContentResult: ...

    @abstractmethod
    async def detect_changes(self, since: datetime) -> List[ChangeInfo]: ...

    @abstractmethod
    async def get_status(self) -> ConnectorStatus: ...
```

#### 3B. File Server Connector

First concrete connector — file server access (SMB/CIFS, NFS, local mount, S3).

**Files:**
- Create: `autobot-backend/knowledge/connectors/file_server.py` — FileServerConnector
- Test: `autobot-backend/knowledge/connectors/file_server_test.py`

**Features:**
- Connect to mounted file paths (simplest, covers NFS/SMB mounts)
- Recursive directory scanning with glob patterns
- File type detection and appropriate chunking
- Change detection via mtime comparison
- Configurable include/exclude patterns

#### 3C. Web Crawler Connector

Builds on LibrarianAssistant's Playwright integration but as a scheduled connector.

**Files:**
- Create: `autobot-backend/knowledge/connectors/web_crawler.py` — WebCrawlerConnector
- Test: `autobot-backend/knowledge/connectors/web_crawler_test.py`

**Features:**
- Configurable URL list + crawl depth
- Uses existing Playwright service on .25
- Respects robots.txt
- Change detection via content hash + Last-Modified headers
- Sitemap parsing for discovery

#### 3D. Database Connector

Connect to external databases and ingest structured data.

**Files:**
- Create: `autobot-backend/knowledge/connectors/database.py` — DatabaseConnector
- Test: `autobot-backend/knowledge/connectors/database_test.py`

**Features:**
- Support PostgreSQL, MySQL, SQLite (via SQLAlchemy)
- Configurable query or table scan
- Row-level chunking strategy (each row = fact, or grouped by key)
- Change detection via timestamp column or row count
- Schema-aware metadata extraction

#### 3E. Connector API Endpoints

REST API for managing connectors.

**Files:**
- Create: `autobot-backend/api/knowledge_connectors.py` — connector CRUD + sync triggers
- Modify: `autobot-backend/main.py` — register connector router

**Endpoints:**
- `GET /api/knowledge/connectors` — list all configured connectors
- `POST /api/knowledge/connectors` — create new connector
- `GET /api/knowledge/connectors/{id}` — get connector details + status
- `PUT /api/knowledge/connectors/{id}` — update connector config
- `DELETE /api/knowledge/connectors/{id}` — remove connector
- `POST /api/knowledge/connectors/{id}/test` — test connection
- `POST /api/knowledge/connectors/{id}/sync` — trigger manual sync
- `GET /api/knowledge/connectors/{id}/history` — sync history

#### 3F. Connector Scheduler

Extend KnowledgeSyncService to manage connector sync schedules.

**Files:**
- Modify: `autobot-backend/services/knowledge_sync_service.py` — add connector scheduling
- Create: `autobot-backend/knowledge/connectors/scheduler.py` — ConnectorScheduler

**Features:**
- Per-connector cron-like schedules
- Incremental sync (only changed content)
- Sync status tracking (running, last success/failure, next run)
- Concurrency control (max parallel syncs)
- Retry with backoff on failure

---

### Phase 4: Connector Management Frontend

#### 4A. Connector Configuration UI

**Files:**
- Create: `autobot-frontend/src/components/knowledge/connectors/ConnectorManager.vue` — main connector management view
- Create: `autobot-frontend/src/components/knowledge/connectors/ConnectorConfigModal.vue` — create/edit connector dialog
- Create: `autobot-frontend/src/components/knowledge/connectors/ConnectorStatusCard.vue` — individual connector status
- Modify: `autobot-frontend/src/views/KnowledgeView.vue` — add Connectors nav item
- Modify: `autobot-frontend/src/router/index.ts` — add `/knowledge/connectors` route
- Modify: `autobot-frontend/src/stores/useKnowledgeStore.ts` — add connector state
- Modify: `autobot-frontend/src/models/repositories/KnowledgeRepository.ts` — add connector API calls
- Modify: `autobot-frontend/src/types/knowledgeBase.ts` — add connector types

**UI features:**
- Connector cards showing status (healthy/error/syncing), last sync time, document count
- Add connector wizard (type selection → config form → test connection → save)
- Per-connector: sync schedule config, include/exclude patterns, verification mode
- Manual sync trigger button
- Sync history timeline
- Health monitoring dashboard

---

### Phase 5: Observable Research in Knowledge

#### 5A. Research Observation Panel

Integrate the browser observation panel into the Knowledge page for watching Librarian Assistant research live.

**Files:**
- Create: `autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue` — research observation with browser view
- Modify: `autobot-frontend/src/views/KnowledgeView.vue` — add Research tab/panel
- Reuse: `autobot-frontend/src/components/chat/VisualBrowserPanel.vue` — existing browser stream component

**Features:**
- Split view: Knowledge search on left, browser observation on right (like terminal in chat)
- Trigger research from Knowledge search when no local results found
- Watch Librarian Assistant browsing in real-time via the browser stream
- Source cards appear as research finds them (pending verification)
- Accept/reject sources inline as they appear
- Research session history

#### 5B. Research WebSocket Events

Backend support for streaming research progress to the Knowledge page.

**Files:**
- Modify: `autobot-backend/agents/librarian_assistant.py` — emit WebSocket events during research
- Create: `autobot-backend/api/knowledge_research_ws.py` — WebSocket endpoint for research events
- Modify: `autobot-frontend/src/composables/useKnowledgeBase.ts` — add research WebSocket composable

**Events:**
- `research:started` — query received, searching
- `research:result_found` — individual result discovered
- `research:content_extracted` — content extracted from URL
- `research:quality_assessed` — quality score assigned
- `research:pending_review` — source ready for user review (collaborative mode)
- `research:stored` — source stored in KB (autonomous mode)
- `research:completed` — research session finished

---

### Phase 6: Pipeline Cognifiers (Enrichment)

#### 6A. Entity Extraction Implementation

Complete the stubbed entity extraction cognifier.

**Files:**
- Modify: `autobot-backend/knowledge/pipeline/cognifiers/entity_extractor.py`
- Test: `autobot-backend/knowledge/pipeline/cognifiers/entity_extractor_test.py`

#### 6B. Relationship Extraction Implementation

Complete the stubbed relationship extraction cognifier.

**Files:**
- Modify: `autobot-backend/knowledge/pipeline/cognifiers/relationship_extractor.py`
- Test: `autobot-backend/knowledge/pipeline/cognifiers/relationship_extractor_test.py`

#### 6C. Summarizer Implementation

Complete the stubbed summarizer cognifier.

**Files:**
- Modify: `autobot-backend/knowledge/pipeline/cognifiers/summarizer.py`
- Test: `autobot-backend/knowledge/pipeline/cognifiers/summarizer_test.py`

---

## Dependency Graph

```
Phase 1A (Provenance Metadata) ──► Phase 1B (Verification API) ──► Phase 1C (Librarian Verification Mode)
                                          │
                                          ▼
                                   Phase 2A (Verification Queue UI) ──► Phase 2B (Provenance Display)
                                          │
Phase 3A (Connector Base) ──► Phase 3B-D (Concrete Connectors) ──► Phase 3E (Connector API)
         │                                                                    │
         ▼                                                                    ▼
  Phase 3F (Scheduler) ◄─────────────────────────────────────── Phase 4A (Connector UI)
                                          │
                                          ▼
                               Phase 5A-B (Observable Research)

Phase 6A-C (Cognifiers) — independent, can be done in parallel with any phase
```

## Priority Order

1. **Phase 1** — Source Provenance & Verification (foundation for trust)
2. **Phase 2** — Verification Frontend (users can review sources)
3. **Phase 3A** — Connector Base Architecture (enables all connectors)
4. **Phase 3B** — File Server Connector (most requested, simplest)
5. **Phase 3E-F** — Connector API + Scheduler (manage connectors)
6. **Phase 4** — Connector Frontend (users can configure connectors)
7. **Phase 3C** — Web Crawler Connector
8. **Phase 3D** — Database Connector
9. **Phase 5** — Observable Research (enhances UX)
10. **Phase 6** — Pipeline Cognifiers (enrichment layer)

---

## GitHub Issues

| Phase | Issue | Title |
|-------|-------|-------|
| 1 | [#1252](https://github.com/mrveiss/AutoBot-AI/issues/1252) | Source Provenance Metadata & Verification Workflow (Backend) |
| 2 | [#1253](https://github.com/mrveiss/AutoBot-AI/issues/1253) | Source Verification Queue & Provenance Display (Frontend) |
| 3 | [#1254](https://github.com/mrveiss/AutoBot-AI/issues/1254) | Source Connector Framework (Backend Architecture) |
| 4 | [#1255](https://github.com/mrveiss/AutoBot-AI/issues/1255) | Connector Management UI (Frontend) |
| 5 | [#1256](https://github.com/mrveiss/AutoBot-AI/issues/1256) | Observable Research Panel (Live Browser Collaboration) |
| 6 | [#1257](https://github.com/mrveiss/AutoBot-AI/issues/1257) | Pipeline Cognifiers Implementation (Entity/Relationship/Summary) |
