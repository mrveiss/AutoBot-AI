---
type: feat
scope: backend
issue: 21499
---

The work-item release request takes an optional `run_id`. When it is sent and is not the checkout generation on the item, the release is refused with 409 and the item and its fence are left alone, so a release replayed from an earlier checkout cannot end a later one. Without it, the release goes by the generation read under the row lock, as before. The run-cancel path and the release path now share one function that drops a checkout fence of a given generation.
