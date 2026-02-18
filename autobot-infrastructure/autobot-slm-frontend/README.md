# autobot-slm-frontend Infrastructure

> Role: `autobot-slm-frontend` | Node: SLM (.19 / 172.16.168.19) | Ansible role: `slm_manager`

---

## Overview

SLM admin dashboard — Vue 3 UI for fleet management. 30 pages, 15 composables, 66 Vue components. Served as a production nginx build alongside the SLM backend on .19.

Does **not** have its own nginx instance — served by the same nginx that proxies `autobot-slm-backend`. Can coexist with `autobot-frontend` on the same node via nginx `server_name` virtual hosts.

---

## Ports

None — traffic flows through the nginx managed by `autobot-slm-backend`.

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-slm-frontend-build` | oneshot | 1 (runs `npm run build`) |

No long-running service. nginx is owned by `autobot-slm-backend`.

---

## Health Check

```bash
curl -sk https://172.16.168.19/ | grep -o '<title>[^<]*</title>'
# Expected: <title>AutoBot SLM</title>
```

---

## Secrets

None — frontend is a static build. API calls use cookies/JWT headers set by the SLM backend.

---

## Deployment

```bash
# Deploy as part of full SLM deploy
ansible-playbook playbooks/deploy-slm-manager.yml --tags frontend,nginx

# Manual sync + build
./infrastructure/shared/scripts/utilities/sync-to-slm.sh
ssh autobot@172.16.168.19 'cd /opt/autobot/autobot-slm-frontend && npm ci && npm run build'
ssh autobot@172.16.168.19 'sudo rsync -a --delete dist/ /var/www/html/slm/'
```

---

## Known Gotchas

- **Never `npm run dev`** on the VM — production builds only.
- **nginx virtual hosts**: Can coexist with `autobot-frontend` via separate `server_name` blocks on the same port 443 nginx instance. Default fleet keeps them on different nodes (.19 vs .21) for isolation.
- **Shares nginx with slm-backend**: The nginx config for slm-frontend is part of the `slm_manager` role.
- **API base URL**: All SLM API calls use relative URLs proxied by nginx. No hardcoded IPs allowed.

---

## Ansible Role

Handled by the `slm_manager` role (same as `autobot-slm-backend`):
- Build Vue app
- Copy `dist/` to nginx webroot
- nginx config already includes frontend serving
