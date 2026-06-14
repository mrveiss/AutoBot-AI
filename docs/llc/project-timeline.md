---
tags:
  - llc
  - module
  - sprint
  - planning
aliases:
  - LLC Gantt
  - Project Timeline
  - Gantt Chart
status: current
---

# LLC Project Timeline (Gantt)

A timeline / Gantt view for sprint planning and project roadmaps (GH#9020).
Work items render as horizontal bars over a time axis, with dependency arrows,
critical-path highlighting, drag-to-reschedule, zoom, and PNG export.

Reachable from the LLC company sidebar (**Timeline**) at
`/llc/companies/{companyId}/timeline`. The view lists the company's projects and
draws the selected project's timeline.

---

## Planned vs actual dates

The timeline uses **planned** dates — `scheduled_start` / `scheduled_end` on the
work item — which are distinct from the actual `started_at` / `completed_at`
lifecycle timestamps. When a work item has no planned dates, the view falls back
to its actual dates; if neither is set, the item is shown as *unscheduled*.

`scheduled_start` / `scheduled_end` are editable via the existing
`PATCH /api/llc/work-items/{id}` endpoint (an agent or the drag-to-reschedule UI
sets them).

---

## API

### `GET /api/llc/projects/{project_id}/timeline`

Returns the project's work items plus the blocked-by dependency edges and a
critical-path flag per item:

```jsonc
{
  "project_id": "…",
  "items": [
    {
      "id": "…", "identifier": "WI-12", "title": "…", "type": "task",
      "status": "in_progress",
      "scheduled_start": "2026-06-01T00:00:00Z",
      "scheduled_end": "2026-06-08T00:00:00Z",
      "started_at": null, "completed_at": null,
      "on_critical_path": true
    }
  ],
  "edges": [ { "from_id": "<blocker>", "to_id": "<blocked>" } ]
}
```

- **Edges** come from `blocked_by` relations: `from_id` (the blocker) must finish
  before `to_id` (the blocked item) starts.
- **Critical path** is the longest-duration path through the dependency DAG;
  duration is `scheduled_end − scheduled_start` in days (1 day when unscheduled).
  Cycles are tolerated (offending edges are skipped). See
  `llc/services/timeline.py::compute_critical_path`.

### `GET /api/llc/companies/{company_id}/projects`

Flat list of a company's projects — drives the timeline's project picker (also
reused by the project browser).

---

## Implementation

- `autobot-backend/llc/models/work_item.py` — `scheduled_start` / `scheduled_end`
  (migration `20260613_057_llc_work_item_scheduled_dates`)
- `autobot-backend/llc/services/timeline.py` — pure critical-path + duration helpers
- `autobot-backend/llc/api/sprints.py` — timeline + company-projects endpoints
- `autobot-frontend/src/views/llc/GanttTimelineView.vue` — custom SVG Gantt
  (no external Gantt library)

## See Also

- Issue #9020 — Gantt chart + timeline view
- [LLC Module PRD](../planning/PRD_AutoBot_LLC_Module.md)
