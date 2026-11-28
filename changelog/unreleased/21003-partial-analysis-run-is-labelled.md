---
type: fix
scope: analytics
issue: 21003
pr: 21478
---
An indexing run that is killed, fails or is cancelled is now recorded as such, with its reason and, for a supervisor kill, the limit that fired. The Codebase Analytics page and the results routes mark findings from such a run as partial and show when the last completed run finished, instead of presenting them as the complete result, and the page says the results are updating while a reindex runs. A new route, `GET /api/analytics/codebase/index/run-state`, returns the run state for a source, and cancelling a run now stops its worker. A new setting, `AUTOBOT_INDEXING_ABANDON_GRACE_SECONDS` (default 300), sets how long past the hard timeout a run that never reported is still treated as running; stored findings are not deleted or rewritten. When the run state cannot be read, the run-state route answers 503 instead of reporting no run, and the page says the state is unknown and offers a retry instead of showing the findings unlabelled. A run that failed is recorded as failed even when the worker could not record it itself, and when an indexing job finishes between two status checks the page still announces how it ended and refreshes its results.
