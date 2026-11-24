---
type: fix
scope: backend
issue: 21332
pr: 0000
---
A Company OS write route now commits before it answers, so a 2xx always means the write is stored. The session dependency every llc route uses commits after the route body and before the response is sent, and rolls back when the route raises or the commit fails. The three findings routes (scan, promote, dismiss) used to answer 200 and lose their write; creating an agent hire no longer answers 201 when recording it failed. The routes of goals, routines, sprints, work items and budget now commit before they answer too. When a write is saved but a follow-up step after the commit fails, the route still answers success and the failure is logged as a warning, because the change is stored.
