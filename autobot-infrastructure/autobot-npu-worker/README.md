# autobot-npu-worker Infrastructure

> Role: `autobot-npu-worker` | Node: NPU VM (.22 / 172.16.168.22) | Ansible role: `npu-worker`

---

## Overview

Intel NPU inference worker using OpenVINO. Provides hardware-accelerated AI inference for the main backend. The SLM backend calls `http://172.16.168.22:8081/health` to detect NPU capabilities and worker status.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 8081 | HTTP | No (fleet-internal) | NPU worker API + health |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-npu-worker` | systemd | 1 |

---

## Health Check

```bash
curl http://172.16.168.22:8081/health | jq
# Expected: {"status": "healthy", "npu": {"available": true, ...}}
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `tls_cert` | `/etc/autobot/autobot-npu-worker/tls.crt` | Fleet-internal TLS |
| `tls_key` | `/etc/autobot/autobot-npu-worker/tls.key` | Private key |
| `service_auth_token` | `/etc/autobot/autobot-npu-worker.env` | Inter-service auth |

---

## Deployment

```bash
# Deploy NPU worker
ansible-playbook playbooks/deploy-full.yml --tags npu-worker --limit npu_vm

# Restart
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-npu-worker action=restart"

# Manual sync
./infrastructure/shared/scripts/utilities/sync-to-vm.sh npu autobot-npu-worker/
```

---

## Hardware Requirements

- Intel NPU (Meteor Lake or later) or Intel Arc GPU
- OpenVINO runtime installed (handled by Ansible `npu-worker` role)
- Intel Neural Compressor for model quantization

---

## Known Gotchas

- **OpenVINO install**: Not via apt — installed from Intel's package repo. The `npu-worker` Ansible role handles this, including the signed-by key.
- **Driver dependency**: NPU driver must be present before the worker starts. Check `/dev/accel/accel0` exists.
- **Model caching**: Compiled OpenVINO models are cached in `/opt/autobot/autobot-npu-worker/model_cache/`. Cache is not wiped on redeploy.
- **NPU detection flow**: SLM calls worker health → worker reports capabilities → SLM updates node NPU fields in DB.

---

## Ansible Role

Role: `npu-worker` in `autobot-slm-backend/ansible/roles/npu-worker/`

Key tasks:
- Install OpenVINO runtime from Intel APT repo
- Install Python requirements (openvino, neural-compressor)
- Deploy worker code to `/opt/autobot/autobot-npu-worker/`
- Systemd unit install + start
