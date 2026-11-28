---
type: fix
scope: config
issue: 20683
pr: 21397
---
An unparseable `CODEBASE_INDEX_BATCH_SIZE` or `CODEBASE_INDEX_EMBED_BATCH_SIZE` no longer fails at config load; it falls back to the default and logs a warning. With `CODEBASE_INDEX_BATCH_SIZE` unset, indexing now uses the documented 5000 instead of the 100 that the old default of 0 was clamped to.
