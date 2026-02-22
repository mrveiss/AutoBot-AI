# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# AutoBot System Dependencies

This document tracks ALL dependencies across the AutoBot platform for each component and VM.

## Table of Contents
- [SLM Server (.19)](#slm-server-19)
- [Main Backend (.20)](#main-backend-20)
- [Frontend VM (.21)](#frontend-vm-21)
- [NPU Worker (.22)](#npu-worker-22)
- [Redis VM (.23)](#redis-vm-23)
- [AI Stack VM (.24)](#ai-stack-vm-24)
- [Browser Worker (.25)](#browser-worker-25)
- [Python Package Dependencies](#python-package-dependencies)
- [Node.js Package Dependencies](#nodejs-package-dependencies)

---

## SLM Server (.19)

**Purpose:** Fleet management and administration dashboard

### System Packages
```bash
# Core system
curl
gnupg
ca-certificates
python3 (3.10+)
python3-pip
python3-venv
nginx (1.18+)
openssl
software-properties-common
build-essential
postgresql (15+)
postgresql-client
libpq-dev

# Ansible for fleet management (MUST be 2.17+)
# Install from PPA, not default Ubuntu repos
ansible (2.17.14+ from ppa:ansible/ansible)

# Node.js for frontend builds
nodejs (20.x from NodeSource)
# Note: npm is bundled with nodejs from NodeSource
```

### Critical Version Requirements
- **Ansible:** MUST be 2.17+ from PPA
  - Default Ubuntu 22.04 ships 2.10.8 which has module incompatibilities
  - Install: `add-apt-repository ppa:ansible/ansible`
- **Node.js:** 20.x LTS from NodeSource
  - NOT from Ubuntu default repos (outdated)
  - Install: `curl -fsSL https://deb.nodesource.com/setup_20.x | bash -`
- **PostgreSQL:** 15+ recommended
  - Default Ubuntu 22.04 ships PostgreSQL 14
  - For PostgreSQL 15+: Add `apt.postgresql.org` repo

### Python Packages (requirements.txt)
See `autobot-slm-backend/requirements.txt`

Key packages:
- fastapi (0.104+)
- uvicorn[standard] (0.24+)
- sqlalchemy (2.0+)
- asyncpg (0.29+)
- redis (5.0+)
- pydantic (2.5+)
- python-jose[cryptography]
- passlib[bcrypt]
- python-multipart
- aiohttp

### Frontend Packages (package.json)
See `autobot-slm-frontend/package.json`

Key packages:
- vue (3.4+)
- vite (5.0+)
- typescript (5.3+)
- axios
- vue-router (4.2+)
- @heroicons/vue

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - Private key for fleet access
- Permissions: 600
- Must exist on SLM server to manage fleet nodes

---

## Main Backend (.20)

**Purpose:** Core AutoBot backend API and AI agent orchestration

**Environment:** Kali Linux WSL2

### System Packages
```bash
python3 (3.10+)
python3-pip
python3-venv
redis-tools
postgresql-client
curl
git
```

### Ansible Compatibility
- **Local Ansible:** 2.19.4 (Kali default)
- **Note:** Different from SLM server (2.17.14) but compatible
- Target node for Ansible must support ansible-core 2.17+ modules

### Python Packages (requirements.txt)
See `autobot-user-backend/requirements.txt`

Key packages:
- fastapi (0.104+)
- uvicorn[standard] (0.24+)
- redis (5.0+)
- chromadb (0.4+)
- langchain (0.1+)
- openai (1.6+)
- anthropic (0.8+)
- sqlalchemy (2.0+)
- playwright (1.40+)
- celery (5.3+)
- pydantic (2.5+)

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - Must exist for Ansible to manage this node
- Permissions: 600

---

## Frontend VM (.21)

**Purpose:** User-facing Vue 3 application

### System Packages
```bash
nginx (1.18+)
openssl
nodejs (20.x from NodeSource)
# npm bundled with nodejs
```

### Frontend Packages (package.json)
See `autobot-user-frontend/package.json`

Key packages:
- vue (3.4+)
- vite (5.0+)
- typescript (5.3+)
- vue-router (4.2+)
- pinia (2.1+)
- axios
- chart.js
- @headlessui/vue
- @heroicons/vue

### Nginx Configuration
- Proxy to backend: https://172.16.168.20:8443
- WebSocket support for /ws endpoint
- TLS certificates: `/etc/ssl/certs/autobot.{crt,key}`

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - For Ansible management
- Permissions: 600

---

## NPU Worker (.22)

**Purpose:** Hardware AI acceleration via Intel NPU

### System Packages
```bash
python3 (3.10+)
python3-pip
python3-venv

# Intel OpenVINO (optional - for NPU acceleration)
# Repository: https://apt.repos.intel.com/openvino/2024
openvino-libraries (2024.0+)
openvino-dev (2024.0+)
```

### Python Packages
See `autobot-npu-worker/requirements.txt`

Key packages:
- fastapi (0.104+)
- uvicorn[standard] (0.24+)
- openvino (2024.0+)
- numpy
- pillow

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - For Ansible management
- Permissions: 600

---

## Redis VM (.23)

**Purpose:** Data layer - caching, sessions, message queues

### System Packages
```bash
# Redis Stack (includes Redis + modules)
# Repository: https://packages.redis.io/deb
redis-stack-server (7.2+)
```

### Configuration
- Port: 6379
- Bind: 0.0.0.0 (accessible to all VMs)
- Maxmemory: 2GB
- Eviction policy: allkeys-lru

### Redis Modules (included in redis-stack)
- RedisJSON
- RedisSearch
- RedisGraph
- RedisTimeSeries
- RedisBloom

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - For Ansible management
- Permissions: 600

---

## AI Stack VM (.24)

**Purpose:** LLM processing and AI model hosting

### System Packages
```bash
python3 (3.10+)
python3-pip
python3-venv
curl
```

### Python Packages
See `autobot-ai-stack/requirements.txt` (if exists)

Key packages:
- transformers (4.35+)
- torch (2.1+)
- sentence-transformers
- accelerate

### Optional: Ollama
- Ollama (latest) for local LLM hosting
- Install: `curl -fsSL https://ollama.com/install.sh | sh`
- Models: llama2, mistral, codellama

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - For Ansible management
- Permissions: 600

---

## Browser Worker (.25)

**Purpose:** Web automation via Playwright

### System Packages
```bash
python3 (3.10+)
python3-pip
python3-venv

# Playwright browser dependencies
libnss3
libnspr4
libatk1.0-0
libatk-bridge2.0-0
libcups2
libdrm2
libxkbcommon0
libxcomposite1
libxdamage1
libxfixes3
libxrandr2
libgbm1
libasound2
```

### Python Packages
See `autobot-browser-worker/requirements.txt`

Key packages:
- fastapi (0.104+)
- uvicorn[standard] (0.24+)
- playwright (1.40+)
- beautifulsoup4
- lxml

### Playwright Browsers
```bash
# After installing playwright package:
python3 -m playwright install chromium
python3 -m playwright install firefox
python3 -m playwright install webkit
```

### Service Name
- **IMPORTANT:** Service is named `autobot-playwright`, NOT `autobot-browser-worker`
- Ansible playbooks MUST use correct service name

### SSH Keys
- `/home/autobot/.ssh/autobot_key` - For Ansible management
- Permissions: 600

---

## Python Package Dependencies

### Backend Common (autobot-shared)
```python
# See autobot-shared/requirements.txt
redis>=5.0.0
pydantic>=2.5.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

### User Backend
```python
# See autobot-user-backend/requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
asyncpg>=0.29.0
redis>=5.0.0
chromadb>=0.4.0
langchain>=0.1.0
openai>=1.6.0
anthropic>=0.8.0
playwright>=1.40.0
celery>=5.3.0
pydantic>=2.5.0
python-multipart>=0.0.6
aiohttp>=3.9.0
```

### SLM Backend
```python
# See autobot-slm-backend/requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
asyncpg>=0.29.0
redis>=5.0.0
pydantic>=2.5.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
aiohttp>=3.9.0
```

---

## Node.js Package Dependencies

### User Frontend
```json
{
  "vue": "^3.4.0",
  "vite": "^5.0.0",
  "typescript": "^5.3.0",
  "vue-router": "^4.2.0",
  "pinia": "^2.1.0",
  "axios": "^1.6.0",
  "chart.js": "^4.4.0",
  "@headlessui/vue": "^1.7.0",
  "@heroicons/vue": "^2.1.0"
}
```

### SLM Frontend
```json
{
  "vue": "^3.4.0",
  "vite": "^5.0.0",
  "typescript": "^5.3.0",
  "axios": "^1.6.0",
  "vue-router": "^4.2.0",
  "@heroicons/vue": "^2.1.0"
}
```

---

## Network Dependencies

### Required Connectivity
All VMs must be able to reach:
- **Redis (.23):** Port 6379
- **Main Backend (.20):** Port 8001
- **SLM Server (.19):** Port 443 (HTTPS + WebSocket)
- **Frontend VM (.21):** Port 443 (HTTPS)

### SSH Access
- All fleet nodes (.19-.27) must accept SSH from SLM server
- SSH key: `autobot_key` (not default `id_rsa`)
- SSH user: `autobot`

---

## Critical Configuration Files

### Ansible
- `autobot-slm-backend/ansible/ansible.cfg` - Ansible configuration
- `autobot-slm-backend/ansible/inventory/slm-nodes.yml` - Fleet inventory
- **Inventory must specify:** `ansible_ssh_private_key_file: ~/.ssh/autobot_key`

### Environment Variables
- `AUTOBOT_BASE_DIR` - Base directory (default: `/opt/autobot`)
- `SLM_ANSIBLE_DIR` - Ansible directory (default: `/opt/autobot/autobot-slm-backend/ansible`)
- `REDIS_HOST` - Redis server IP (172.16.168.23)
- `POSTGRES_HOST` - PostgreSQL server IP (172.16.168.19 for SLM)

---

## Version Compatibility Matrix

| Component | Ubuntu 22.04 | Kali Rolling | Notes |
|-----------|--------------|--------------|-------|
| Python | 3.10+ | 3.11+ | ✅ Compatible |
| Ansible (control) | 2.17.14 (PPA) | 2.19.4 | ✅ Compatible |
| Ansible (target) | 2.17+ modules | 2.17+ modules | ⚠️ MUST upgrade SLM from 2.10.8 |
| Node.js | 20.x (NodeSource) | 20.x | ✅ Compatible |
| PostgreSQL | 14 (default) / 15+ (repo) | 15+ | ✅ Compatible |
| Redis | 7.2+ (redis-stack) | 7.2+ | ✅ Compatible |

---

## Installation Order (Fresh Setup)

1. **System packages** (OS-level dependencies)
2. **Package repositories** (NodeSource, Ansible PPA, PostgreSQL repo)
3. **Python venv setup** (create + activate virtual environment)
4. **Python packages** (`pip install -r requirements.txt`)
5. **Node.js packages** (`npm install`)
6. **Playwright browsers** (`playwright install`)
7. **Database initialization** (PostgreSQL tables, Redis config)
8. **SSH keys deployment** (distribute `autobot_key` to all nodes)
9. **Systemd services** (backend, workers, nginx)
10. **TLS certificates** (self-signed or Let's Encrypt)

---

## Troubleshooting

### Ansible "No module named 'ansible.module_utils.six.moves'"
- **Cause:** Ansible version mismatch between control and target
- **Fix:** Upgrade control node to Ansible 2.17+ from PPA
- **Command:** `add-apt-repository ppa:ansible/ansible && apt install ansible`

### Frontend build fails with "vite warnings"
- **Cause:** `npm-run-all` treats warnings as errors
- **Fix:** Use `npx vite build` directly instead of `npm run build`

### Service name not found: autobot-browser-worker
- **Cause:** Service is actually named `autobot-playwright`
- **Fix:** Update playbooks to use correct service name

### SSH key not found: id_rsa
- **Cause:** AutoBot uses `autobot_key`, not default `id_rsa`
- **Fix:** Ensure `autobot_key` exists on all nodes with permissions 600

---

## Maintenance Notes

### When Adding a New VM
1. Copy SSH key: `ssh-copy-id -i ~/.ssh/autobot_key autobot@<new-ip>`
2. Add to `slm-nodes.yml` inventory
3. Run provisioning: `ansible-playbook provision-fleet-roles.yml --limit <new-node>`

### When Upgrading System Packages
1. Test on non-production node first (.26 or .27)
2. Clear Ansible fact cache: `rm /tmp/ansible_fact_cache/<host>`
3. Run update playbook: `ansible-playbook update-all-nodes.yml --limit <node>`
4. Verify services: `systemctl status <service-name>`

### When Upgrading Python Packages
1. Update `requirements.txt` with new versions
2. Test in venv: `pip install -r requirements.txt`
3. Sync to target nodes via Ansible
4. Restart services

---

## References

- [Official Ansible Docs](https://docs.ansible.com/)
- [NodeSource Node.js Distributions](https://github.com/nodesource/distributions)
- [Vue 3 Documentation](https://vuejs.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Playwright Documentation](https://playwright.dev/python/)
