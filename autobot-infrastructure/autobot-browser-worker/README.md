# autobot-browser-worker Infrastructure

> Role: `autobot-browser-worker` | Node: Browser VM (.25 / 172.16.168.25) | Ansible role: `browser`

---

## Overview

Playwright-based browser automation worker. Executes web scraping, GUI automation, screenshot capture, and CAPTCHA-solving workflows on behalf of the main backend.

**Note**: The systemd service is named `autobot-playwright` (not `autobot-browser-worker`).

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 3000 | HTTP | No (fleet-internal) | Browser worker API |

**Warning**: Port 3000 also used by Grafana in `autobot-monitoring`. These roles must be on different nodes.

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-playwright` | systemd | 1 |

---

## Health Check

```bash
curl http://172.16.168.25:3000/health | jq
# Expected: {"status": "healthy", "browsers": {...}}
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `tls_cert` | `/etc/autobot/autobot-browser-worker/tls.crt` | Fleet-internal TLS |
| `tls_key` | `/etc/autobot/autobot-browser-worker/tls.key` | Private key |
| `service_auth_token` | `/etc/autobot/autobot-browser-worker.env` | Inter-service auth |

---

## Deployment

```bash
# Deploy browser worker
ansible-playbook playbooks/deploy-full.yml --tags browser --limit browser_vm

# Restart (use correct service name!)
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-playwright action=restart"

# Manual sync
./infrastructure/shared/scripts/utilities/sync-to-vm.sh browser autobot-browser-worker/
```

---

## Known Gotchas

- **Service name is `autobot-playwright`**: Not `autobot-browser-worker`. Using the wrong name in systemctl calls will fail silently.
- **Port 3000 conflict with monitoring**: monitoring (Grafana) also uses port 3000. Both are on different nodes by default. See COEXISTENCE_MATRIX.md.
- **Playwright install**: Playwright browsers (~400MB) must be downloaded after install. The `browser` Ansible role runs `playwright install chromium` after pip install.
- **Display required**: Some automation requires a virtual display. The `browser` role installs `xvfb` and configures `DISPLAY=:99`.
- **CAPTCHA human-in-the-loop**: Browser worker integrates with `captcha_human_loop.py` — needs a running main backend to relay CAPTCHA challenges.

---

## Ansible Role

Role: `browser` in `autobot-slm-backend/ansible/roles/browser/`

Key tasks:
- Install system packages (xvfb, libnss3, etc.)
- Install Python + playwright
- Run `playwright install chromium`
- Systemd unit named `autobot-playwright`
- Configure DISPLAY + dbus
