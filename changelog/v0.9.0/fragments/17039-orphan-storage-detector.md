---
type: feat
scope: backend
issue: 17039
pr: 0
---
A backend framework (`services/orphan_storage.py`) in which a data-owning module registers a read-only orphan-storage detector -- `provider`, `id`, a logical `location` (never a host path), `size_bytes`, `modified_at`, `reason`, `deletable`. The first detector (`api/codebase_analytics/orphan_clone_detector.py`) finds code-source clone directories with no matching source record, excluding anything younger than `AUTOBOT_ORPHAN_GRACE_HOURS` (default 24, clamped to 1-720), and re-checks orphan status and the grace period again at delete time. `GET /api/admin/orphan-storage` (admin-only) previews candidates across every registered detector; deletion is not exposed as a bare admin route, since the owner's rule requires every removal to go through a human-approved review queue (#17043) that will call the delete-through-owner function once it lands. Also fixes #17036: `api/codebase_analytics/source_service.py`'s and `endpoints/sources.py`'s clone-directory removal no longer swallows a failed `rmtree` with `ignore_errors=True` -- a failure is logged and reported, and the source record is marked `cleanup_failed` rather than dropped while the directory survives.
