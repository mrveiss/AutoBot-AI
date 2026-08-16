---
type: fix
scope: chat
issue: 14066
pr: 14249
---
Context compaction now cuts at a turn boundary, carries recent user messages across verbatim, and emits a deterministic state block (files written, commands run, tools used) alongside the model's summary, so a bad summarisation turn no longer takes the session's state with it.
