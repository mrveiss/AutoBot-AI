# Docker Directory - DEPRECATED

**Issue:** #725
**Date:** 2026-01-29
**Status:** Deprecated - Not Used in Production

---

## Notice

The contents of this directory are **DEPRECATED** and **NOT USED** in the current AutoBot deployment.

All services now run **natively via systemd** on their respective machines, not in Docker containers.

---

## Current Service Deployment

| Service | Role | IP | Deployment Method |
|---------|------|-----|-------------------|
| Backend | Main / control host | ${AUTOBOT_*_HOST}.20 | systemd: `autobot-backend.service` |
| AI Stack | AI/ML | ${AUTOBOT_*_HOST}.24 | systemd: `autobot-ai-stack.service` |
| NPU Worker | AI/ML (NPU worker) | ${AUTOBOT_*_HOST}.22 | systemd: `autobot-npu-worker.service` |
| Redis Stack | Database | ${AUTOBOT_*_HOST}.23 | systemd: `redis-stack-server.service` |
| Frontend | Frontend | ${AUTOBOT_*_HOST}.21 | systemd or Vite dev server |
| Browser | Browser | ${AUTOBOT_*_HOST}.25 | systemd: Playwright service |

> This is one install's historical layout, recorded when this directory was deprecated. AutoBot's
> architecture is role-based and count-agnostic — a deployment may run in Docker, on one VM, or
> scaled across any number of machines.

---

## Why Docker is Not Used

1. **Performance** - Native execution provides better performance for AI/ML workloads
2. **Hardware Access** - Direct NPU/GPU access without container overhead
3. **Simplicity** - Systemd provides simpler service management
4. **Debugging** - Easier to debug without container abstraction layer

---

## Contents (For Reference Only)

- `ai-stack/` - Legacy Docker config for AI Stack container
- `npu-worker/` - Legacy Docker config for NPU Worker container
- `compose/` - Legacy Docker Compose configurations

---

## Do Not Use

These Docker configurations are outdated and may not work with current code.

For deployment instructions, see:
- `ansible/playbooks/deploy-native-services.yml`
- `docs/developer/INFRASTRUCTURE_DEPLOYMENT.md`
