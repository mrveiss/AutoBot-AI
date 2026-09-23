---
type: fix
scope: ci
issue: 16931
pr: 0000
---
The commit-trailer gate now fetches full history for a PR deeper than 90 commits. A release promotion carries every commit since the last release, so a fixed `fetch-depth: 100` left most of it unexamined and the gate — correctly — refused to report the truncated range as clean. Ordinary PRs keep depth 100, so the cost saving from #16207 is unchanged.
