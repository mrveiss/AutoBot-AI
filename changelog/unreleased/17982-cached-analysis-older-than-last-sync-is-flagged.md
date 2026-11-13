---
type: fix
scope: analytics
issue: 17982
pr: 21478
---
A cached dependencies, duplicates or import-tree result that was produced before the source's most recent sync is still served, but is now flagged `stale`, and the page says it predates the last sync. The flag follows every sync, including a sync that changed nothing.
