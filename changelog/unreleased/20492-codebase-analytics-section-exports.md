---
type: fix
scope: frontend
issue: 20492
pr: 21397
---
Section exports in Codebase Analytics (Markdown and JSON) are generated from the same data each panel shows. The declarations, API endpoints, cross-language, config duplicates and code intelligence exports previously read fields that did not exist and printed empty or "undefined" rows.
