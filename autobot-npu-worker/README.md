# AutoBot NPU Worker

> **Deploys to:** 172.16.168.22 (NPU VM)

Hardware AI acceleration worker using Intel NPU/OpenVINO.

## Status

**Stub** - NPU-specific code will be extracted from main backend in a future phase.

## Deployment

```bash
./infrastructure/shared/scripts/sync-to-vm.sh npu autobot-npu-worker/
```

## Infrastructure

Component-specific infrastructure is located at:

```text
infrastructure/autobot-npu-worker/
├── docker/      # Docker configurations
├── tests/       # Component-specific tests
├── config/      # Configuration files
├── scripts/     # Deployment scripts
└── templates/   # Service templates
```
