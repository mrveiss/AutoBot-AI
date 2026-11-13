---
type: fix
scope: analytics
issue: 20513
pr: 21478
---
`GET /api/analytics/codebase/index/current` now requires `source_id` and answers only for that source's job, including a request for a job still queued behind another source's job; a call without `source_id` gets a 422 response. On the page, switching source while a job is being polled no longer shows the previous source's job or results, and Stop is unavailable until there is a job of the selected source to stop.
