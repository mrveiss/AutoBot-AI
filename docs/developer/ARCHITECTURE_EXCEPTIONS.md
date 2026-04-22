# Architecture Exceptions

This document records intentional deviations from the standard AutoBot architecture.
Each entry explains what diverges, which canonical module it mirrors, why the exception
exists, and how to keep the two in sync.

---

## Windows NPU Worker — Standalone Redis Client

**File:** `autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py`
**Mirrors:** `autobot_shared/redis_client.py`
**Issue:** #5438

**Reason:** The Windows NPU worker is packaged as a self-contained executable via PyInstaller.
It cannot import from `autobot_shared/` at runtime because the shared package is not bundled
with the executable. The standalone redis_client.py replicates the subset of functionality
needed by the worker.

**Sync cadence:** When `autobot_shared/redis_client.py` changes (connection parameters,
retry logic, health-check helpers), manually mirror those changes here. Reference this
document to surface the obligation.
