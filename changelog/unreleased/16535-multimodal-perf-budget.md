---
type: fix
scope: testing
issue: 16535
pr: 0
---
`Multimodal processor startup`'s performance budget is re-derived from seven real post-#15297 measurements (2013-4348 work units) instead of the stale #15054-era baseline (315.602 units, taken while CLIP loading was silently short-circuiting) — the marker-excluded suite was failing this assertion on most runs, blocking `#13286`'s ten-consecutive-green bar for enabling its scheduled cron.
