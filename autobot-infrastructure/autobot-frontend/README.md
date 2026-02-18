# autobot-frontend Infrastructure

> Role: `autobot-frontend` | Node: Frontend VM (.21 / 172.16.168.21) | Ansible role: `frontend`

---

## Overview

Vue 3 user-facing chat interface. Served as a production nginx build. All backend API calls are proxied through nginx — the frontend never talks directly to the backend IP.

Conflicts with `autobot-slm-frontend`: both bind port 443. Must be on separate nodes.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 443 | HTTPS | Yes | Frontend + nginx reverse proxy to backend |
| 80 | HTTP | Yes | Redirect to 443 |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-frontend-build` | oneshot | 1 (runs `npm run build`) |
| `autobot-frontend` | systemd | 2 (nginx) |

---

## Health Check

```bash
curl -sk https://172.16.168.21/ | grep -o '<title>[^<]*</title>'
# Expected: <title>AutoBot</title>
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `tls_cert` | `/etc/ssl/autobot/frontend.crt` | Signed by SLM CA |
| `tls_key` | `/etc/ssl/autobot/frontend.key` | Private key (mode 640) |

No application secrets — frontend is a static build. Backend auth handled via cookie/header proxied through nginx.

---

## Deployment

```bash
# Full build + deploy (from autobot-slm-backend/ansible/)
ansible-playbook playbooks/deploy-full.yml --tags frontend --limit frontend_vm

# nginx reload only (config change)
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-frontend action=reload"

# Manual sync + build
./infrastructure/shared/scripts/utilities/sync-to-vm.sh frontend autobot-frontend/
ssh autobot@172.16.168.21 'cd /opt/autobot/autobot-frontend && npm ci && npm run build'
ssh autobot@172.16.168.21 'sudo rsync -a --delete dist/ /var/www/html/'
```

---

## nginx Proxy Config

nginx on .21 proxies `/api/` and `/ws/` to `https://172.16.168.20:8443`. This means:
- The frontend always uses relative URLs (no hardcoded backend IPs)
- TLS termination happens at nginx
- The browser only ever connects to .21

---

## Known Gotchas

- **Never `npm run dev`** on the VM — production builds only.
- **nginx dir ownership**: `/var/www/html/` is owned by `www-data`. Fix with `sudo chown -R autobot:autobot /var/www/html/` before rsync.
- **`VITE_API_BASE_URL` must NOT be set** in `.env` — if set, it bakes a hardcoded IP into the bundle bypassing nginx proxy mode.
- **Conflicts with slm-frontend**: Both bind port 443. They live on different nodes (.21 vs .19).

---

## Ansible Role

Role: `frontend` in `autobot-slm-backend/ansible/roles/frontend/`

Key tasks:
- Install Node.js via NodeSource (bundles npm — do NOT install npm via apt)
- Run `npm ci && npm run build`
- Rsync `dist/` → `/var/www/html/`
- Render nginx config from `templates/nginx.conf.j2`
- Reload nginx
