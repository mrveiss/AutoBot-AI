# Agent Admin Panels Design

> Issues: #1404 (frontend), #1405 (frontend), #1406 (frontend)
> Target: SLM frontend (`autobot-slm-frontend/`) at `/agents`
> Date: 2026-03-15

## Context

Backend APIs for config audit trail (#1404), agent org charts (#1405), and process adapters (#1406) are complete. The remaining work is 3 admin frontend panels in the SLM dashboard.

## Architecture

**Location:** SLM frontend (`autobot-slm-frontend/src/`), extending `views/AgentsView.vue`.

**API proxy:** All calls use `/autobot-api/...` which Vite/nginx proxies to main backend on .20:8001 → `/api/...`. This proxy is already configured in `vite.config.ts` (Issue #729).

**Pattern:** Each panel is a standalone Vue 3 SFC imported into AgentsView as a tab, matching the existing `ExternalAgentsView` pattern.

## Component Structure

```
autobot-slm-frontend/src/
  views/AgentsView.vue              — add 3 tab buttons + v-if blocks
  components/agents/
    OrgChartTab.vue                 — tree view + delegation
    ConfigHistoryTab.vue            — revision timeline + diff + rollback
    ProcessMonitorTab.vue           — process table + log viewer
```

## Tab 1: Org Chart (#1405)

**Endpoints:**
- `GET /autobot-api/agents/org` — full recursive tree
- `GET /autobot-api/agents/{id}/chain` — chain of command
- `GET /autobot-api/agents/{id}/reports` — direct reports
- `PATCH /autobot-api/agents/{id}/org` — update reporting line
- `POST /autobot-api/agents/{id}/delegate` — assign task
- `GET /autobot-api/agents/{id}/activity` — delegation summary
- `GET /autobot-api/agents/{id}/delegations` — delegation list

**UI:**
- Indented tree view (not a drag-drop graph — keep it simple)
- Each node shows: name, role badge, title, direct reports count
- Click node → side panel with chain of command, direct reports list, delegation form
- Delegation form: select assignee from direct reports, enter task description, submit
- Activity summary: counts by delegation status (pending/completed/failed/escalated)

## Tab 2: Config History (#1404)

**Endpoints:**
- `GET /autobot-api/config-revisions/{entity_type}/{entity_id}` — paginated list
- `GET /autobot-api/config-revisions/{entity_type}/{entity_id}/{rev_id}` — single with diff
- `POST /autobot-api/config-revisions/{entity_type}/{entity_id}/{rev_id}/rollback` — restore

**UI:**
- Entity selector: dropdown for entity_type (agent/system) + entity_id (agent name or settings/config/backend)
- Timeline list of revisions: source badge, created_by, changed_keys summary, timestamp
- Click revision → modal/expandable with before/after JSON diff (side-by-side or inline)
- Rollback button on each revision → confirm dialog → calls rollback endpoint
- Changed keys highlighted in diff view

## Tab 3: Process Monitor (#1406)

**Endpoints:**
- `GET /autobot-api/agents/{id}/processes` — list with status filter
- `GET /autobot-api/processes/{id}` — single process status
- `GET /autobot-api/processes/{id}/logs` — full log output
- `POST /autobot-api/processes/spawn` — start new process
- `POST /autobot-api/processes/{id}/signal` — send SIGTERM/SIGKILL

**UI:**
- Agent selector dropdown (from agent list)
- Process table: command, status badge, exit code, duration, started_at
- Status badges: queued (gray), running (blue pulse), completed (green), failed (red), timed_out (orange)
- Click process → expandable log viewer showing log_excerpt (8KB preview)
- "View Full Log" button → modal with full log from /logs endpoint
- Kill button (SIGTERM) on running processes, with confirm dialog
- Spawn form: agent_id, command, args, timeout (for admin testing)

## Styling

Match existing AgentsView patterns:
- White card containers with `border-radius: 12px`, `box-shadow: 0 1px 3px rgba(0,0,0,0.1)`
- CSS variables: `var(--text-primary)`, `var(--text-secondary)`, `var(--primary)`
- Status badges: small colored pills
- Scoped `<style scoped>` per component
- No component library — plain HTML + CSS matching existing SLM frontend style

## WebSocket (deferred)

Real-time log streaming (#1406) requires a WebSocket endpoint on the main backend. This is deferred — the initial implementation uses polling via REST `/logs` endpoint. A future issue can add WebSocket streaming.
