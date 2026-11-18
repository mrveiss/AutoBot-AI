---
type: fix
scope: backend
issue: 19630
pr: 19667
---
A member removed from a team, or a deleted team, stops granting that team's knowledge facts in every worker at once, and team lookups are scoped to the active organisation.
