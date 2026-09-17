---
type: fix
scope: infra
issue: 14288
pr: 0000
---
`cleanup-nodes.yml`'s NPU-worker and browser-automation cleanup plays now target the hyphenated-free group names an inventory actually emits (`npu_worker`, `browser_worker:browser_automation`) instead of `npu-worker`/`browser-automation`, which no inventory builder produces — both plays had never run.
