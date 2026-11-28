---
type: fix
scope: code-intelligence
issue: 21317
pr: 21397
---
A call edge now keeps every distinct call-site line instead of only the first, up to `AUTOBOT_CODE_INDEX_MAX_CALL_SITES_PER_EDGE` (default 50), with a count of dropped sites. Records written before the change are still read.
