# AutoBot Browser Worker

> **Deploys to:** 172.16.168.25 (Browser VM)

Playwright-based browser automation worker.

## Status

**Stub** - Browser automation code will be extracted from main backend in a future phase.

## Deployment

```bash
./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
```

## Infrastructure

Component-specific infrastructure is located at:

```text
infrastructure/autobot-browser-worker/
├── docker/      # Docker configurations
├── tests/       # Component-specific tests
├── config/      # Configuration files
├── scripts/     # Deployment scripts
└── templates/   # Service templates
```
