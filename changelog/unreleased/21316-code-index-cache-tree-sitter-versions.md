---
type: fix
scope: code-intelligence
issue: 21316
pr: 21397
---
The code index extraction cache version now includes the installed tree-sitter and grammar package versions, so a grammar upgrade no longer serves stale extractions; the graph provenance record carries those versions. Existing caches are invalidated once, and a graph written before the change reads as not current until the next index run.
