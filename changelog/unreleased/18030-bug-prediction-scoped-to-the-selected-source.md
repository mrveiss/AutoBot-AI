---
type: fix
scope: analytics
issue: 18030
pr: 22085
---
Bug prediction now analyses only the selected code source: its routes require `source_id`, no longer take a filesystem `path`, and keep results, history and recorded bugs per source. A cached reply is marked `from_cache` and flagged `stale` when it predates the source's last sync, and an `include_pattern` that is absolute, contains `..` or a NUL byte, or is too long is refused with 422.
