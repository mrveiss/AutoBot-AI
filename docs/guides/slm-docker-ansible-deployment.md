# Deploying Docker Containers via SLM Ansible Playbooks


## Quick Answer

**How do you deploy a Docker container using the SLM and an Ansible playbook?**

Use the SLM API to trigger an Ansible playbook that deploys a Docker container to a
fleet node. The flow is: authenticate with the SLM, write an Ansible playbook for
Docker deployment, execute it via the `/api/playbooks/execute` endpoint. Here is the
complete end-to-end example:

**1. Authenticate with the SLM:**

```bash
SLM_TOKEN=$(curl -sk -X POST https://172.16.168.19/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**2. Create the Ansible playbook** (`ansible/playbooks/deploy-docker-app.yml`):

```yaml
---
- name: Deploy Docker container to fleet node
  hosts: "{{ target_hosts | default('ai_stack') }}"
  become: true
  vars:
    container_name: "{{ app_name | default('my-app') }}"
    container_image: "{{ image | default('nginx:latest') }}"
    container_port: "{{ port | default('8080') }}"
    host_port: "{{ host_port_map | default('8080') }}"
  tasks:
    - name: Ensure Docker is installed
      ansible.builtin.apt:
        name: [docker.io, docker-compose-v2]
        state: present
        update_cache: true

    - name: Pull container image
      community.docker.docker_image:
        name: "{{ container_image }}"
        source: pull

    - name: Deploy container
      community.docker.docker_container:
        name: "{{ container_name }}"
        image: "{{ container_image }}"
        state: started
        restart_policy: unless-stopped
        ports:
          - "{{ host_port }}:{{ container_port }}"
        env:
          AUTOBOT_NODE: "{{ inventory_hostname }}"

    - name: Verify container is running
      ansible.builtin.command: docker inspect --format='{{ '{{' }}.State.Status{{ '}}' }}' {{ container_name }}
      register: container_status
      changed_when: false

    - name: Assert container is running
      ansible.builtin.assert:
        that: container_status.stdout == "running"
        fail_msg: "Container {{ container_name }} is not running"
```

**3. Execute via the SLM API:**

```python
import aiohttp
import asyncio


async def deploy_docker_via_slm():
    """Deploy a Docker container to a fleet node using the SLM API."""
    slm_url = "https://172.16.168.19"

    async with aiohttp.ClientSession() as session:
        # Authenticate
        auth_resp = await session.post(
            f"{slm_url}/api/auth/login",
            json={"username": "admin", "password": "your_password"},
            ssl=False,
        )
        token = (await auth_resp.json())["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Execute the playbook
        resp = await session.post(
            f"{slm_url}/api/playbooks/execute",
            json={
                "playbook": "deploy-docker-app.yml",
                "extra_vars": {
                    "target_hosts": "ai_stack",
                    "app_name": "my-web-app",
                    "image": "nginx:1.25",
                    "port": "80",
                    "host_port_map": "8080",
                },
            },
            headers=headers,
            ssl=False,
        )
        result = await resp.json()
        execution_id = result["execution_id"]

        # Poll for completion
        while True:
            status_resp = await session.get(
                f"{slm_url}/api/playbooks/status/{execution_id}",
                headers=headers,
                ssl=False,
            )
            status = await status_resp.json()
            print(f"Status: {status['status']}")
            if status["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(3)

        return status


asyncio.run(deploy_docker_via_slm())
```

**4. Verify:**

```bash
curl -sk -H "Authorization: Bearer $SLM_TOKEN" \
  https://172.16.168.19/api/nodes | python3 -m json.tool
ssh autobot@172.16.168.24 "docker ps --filter name=my-web-app"
```

For rolling deployments, inventory configuration, and node lifecycle management,
see [Section 8](#8-rolling-deployment-strategy) and [Section 10](#10-complete-end-to-end-example).

---


> **Benchmark:** Use the Service Lifecycle Manager to automate the deployment of a Docker container using an Ansible playbook.

AutoBot's primary deployment model uses systemd services managed via Ansible. However, the SLM's Ansible playbook execution engine supports **any** deployment strategy, including Docker containers. This guide shows how to use the SLM API to deploy Docker containers to fleet nodes via Ansible playbooks. It covers SLM architecture, node lifecycle management, authentication, playbook authoring, API-driven execution, inventory configuration, rolling deployment strategies, operational gotchas, and a complete end-to-end example with verification.

> **Note:** AutoBot's core services currently run as systemd units, not Docker containers. This guide demonstrates how to extend the fleet with Docker-based workloads using the same SLM infrastructure.

---

## Table of Contents

1. [SLM Architecture for Deployment](#1-slm-architecture-for-deployment)
2. [Node State Machine](#2-node-state-machine)
3. [SLM Authentication](#3-slm-authentication)
4. [Creating an Ansible Playbook for Docker Deployment](#4-creating-an-ansible-playbook-for-docker-deployment)
5. [Deploying via the SLM API](#5-deploying-via-the-slm-api)
6. [SLM API Endpoint Reference](#6-slm-api-endpoint-reference)
7. [Inventory Configuration](#7-inventory-configuration)
8. [Rolling Deployment Strategy](#8-rolling-deployment-strategy)
9. [Operational Gotchas](#9-operational-gotchas)
10. [Complete End-to-End Example](#10-complete-end-to-end-example)
11. [Verification Checklist](#11-verification-checklist)

---

## 1. SLM Architecture for Deployment

The Service Lifecycle Manager (SLM) is AutoBot's centralized fleet management system. It runs on the admin machine (172.16.168.19) and orchestrates all infrastructure operations --- including Docker container deployments --- across the fleet via Ansible.

### Architectural Overview

```
+---------------------------------------------------------------+
|                   SLM Server (172.16.168.19)                   |
|                                                                |
|  +-------------------+    +-------------------+               |
|  | FastAPI Backend    |    | Vue.js Admin UI   |               |
|  | (uvicorn :8000)    |    | (nginx :443)      |               |
|  +--------+----------+    +-------------------+               |
|           |                                                    |
|  +--------v----------+    +-------------------+               |
|  | PlaybookExecutor   |    | DeploymentService |               |
|  | (ansible-playbook) |    | (async tasks)     |               |
|  +--------+----------+    +--------+----------+               |
|           |                         |                          |
|  +--------v-------------------------v----------+               |
|  |          PostgreSQL Database                |               |
|  |  (nodes, deployments, roles, events, ...)   |               |
|  +---------------------------------------------+               |
+---------------------------------------------------------------+
          |           |           |           |
     SSH + mTLS  SSH + mTLS  SSH + mTLS  SSH + mTLS
          |           |           |           |
    +-----v---+ +-----v---+ +-----v---+ +-----v---+
    | .20 Main| | .21 FE  | | .22 NPU | | .24 AI  | ...
    | Backend | | Frontend| | Worker  | | Stack   |
    +---------+ +---------+ +---------+ +---------+
```

### Core Components

| Component | Description |
|-----------|-------------|
| **FastAPI Backend** | REST API on port 8000 (behind nginx reverse proxy on port 443). Handles authentication, node management, playbook execution, and deployment orchestration. |
| **Vue.js Admin UI** | SLM dashboard for visual fleet management, served by nginx with TLS. |
| **PostgreSQL Database** | Persists all state: nodes, deployments, roles, events, certificates, audit logs. Replaced SQLite as of Issue #786. |
| **PlaybookExecutor** | Service class (`autobot-slm-backend/services/playbook_executor.py`) that shells out to `ansible-playbook` as an async subprocess, streams output line-by-line, and parses progress updates. Resolves playbooks relative to `SLM_ANSIBLE_DIR` (default: `/opt/autobot/autobot-slm-backend/ansible`). |
| **DeploymentService** | Service class (`autobot-slm-backend/services/deployment.py`) that manages the deployment lifecycle: creates `Deployment` records in the database, launches Ansible playbooks in background `asyncio.Task`s, tracks status through `PENDING -> IN_PROGRESS -> COMPLETED/FAILED`. |
| **Reconciler** | Background task (60-second interval via `reconcile_interval` setting) that checks node health via heartbeat timeouts and drives state transitions. |

### Management Plane vs Runtime Plane

The SLM enforces a strict separation between management and runtime:

| Aspect | Management Plane (SLM) | Runtime Plane (Fleet Nodes) |
|--------|------------------------|----------------------------|
| **Location** | 172.16.168.19 | 172.16.168.20-27 |
| **Purpose** | Orchestration, monitoring, deployment | Application workloads |
| **Access** | Admin credentials, JWT tokens | SSH key-based (passwordless) |
| **State** | PostgreSQL (persistent) | Stateless (agent heartbeat only) |
| **Ansible** | Controller (runs playbooks) | Targets (receive playbook tasks) |
| **Code source** | Git repo at `/opt/autobot/code_source` | Deployed artifacts via rsync/Ansible |

All configuration changes originate on the management plane. Direct editing on fleet nodes is prohibited --- see [CLAUDE.md](../../CLAUDE.md) for the local-edit-then-sync policy.

### PlaybookExecutor Internals

The `PlaybookExecutor` class is the bridge between the SLM API and Ansible. Key implementation details:

```python
# From autobot-slm-backend/services/playbook_executor.py

class PlaybookExecutor:
    """Execute Ansible playbooks programmatically."""

    def __init__(self, ansible_dir=None):
        # Defaults to /opt/autobot/autobot-slm-backend/ansible
        self.ansible_dir = ansible_dir or Path(
            os.getenv("SLM_ANSIBLE_DIR",
                       "/opt/autobot/autobot-slm-backend/ansible")
        )
        self.inventory_path = self.ansible_dir / "inventory" / "slm-nodes.yml"

    async def execute_playbook(
        self,
        playbook_name: str,             # e.g., "deploy-container.yml"
        limit: list[str] | None = None, # e.g., ["02-Frontend"]
        tags: list[str] | None = None,  # e.g., ["deploy"]
        extra_vars: dict | None = None, # e.g., {"container_image": "nginx"}
        check_mode: bool = False,       # --check (dry run)
        progress_callback=None,         # async callback for progress
        inventory_path: Path | None = None,  # override inventory
    ) -> dict:
        """Returns {"success": bool, "output": str, "returncode": int}"""
```

The executor builds the `ansible-playbook` command, sets environment variables (`ANSIBLE_FORCE_COLOR=0`, `ANSIBLE_HOST_KEY_CHECKING=False`, `ANSIBLE_SSH_RETRIES=3`), and streams stdout line-by-line through an optional progress callback.

---

## 2. Node State Machine

Every fleet node tracked by SLM follows a defined state machine. The `NodeStatus` enum in `autobot-slm-backend/models/database.py` defines all valid states.

### State Definitions

| State | Value | Description |
|-------|-------|-------------|
| **PENDING** | `pending` | Node registered but not yet enrolled. No agent running. |
| **ENROLLING** | `enrolling` | Enrollment playbook is currently executing (deploying SLM agent). |
| **ONLINE** | `online` | Node healthy. Agent sending heartbeats within threshold. |
| **DEGRADED** | `degraded` | Node reachable but one or more optional roles are down or health checks failing. |
| **OFFLINE** | `offline` | Heartbeat missed beyond `unhealthy_threshold` (default: 3 consecutive misses at 30-second intervals). |
| **ERROR** | `error` | Enrollment failed or a critical error occurred during deployment. |
| **MAINTENANCE** | `maintenance` | Manually placed into maintenance mode. Alerts and auto-remediation suppressed. |
| **DECOMMISSIONED** | `decommissioned` | Permanently removed from fleet management. |

### State Transition Diagram

```
                    +-- register node (POST /api/nodes) --+
                    |                                      |
                    v                                      |
              +-----------+                               |
              |  PENDING  |<------------------------------+
              +-----+-----+
                    |
          POST /api/nodes/{id}/enroll
                    |
                    v
             +------------+
             | ENROLLING  |
             +-----+------+
                   / \
                  /   \
        success  /     \  failure
                /       \
               v         v
         +---------+  +-------+
         |  ONLINE |  | ERROR |
         +----+----+  +---+---+
              |            |
              |      re-enroll / fix
              |            |
    +---------+---------+  |
    |         |         |  |
    v         v         v  v
+--------+ +-------+ +----------+
|DEGRADED| |OFFLINE| | PENDING  |
+---+----+ +---+---+ +----------+
    |          |
    |    heartbeat resumes
    |          |
    v          v
+--------+ +---------+
|MAINTEN.| | ONLINE  |
+---+----+ +---------+
    |
  exit maintenance
    |
    v
+---------+
| ONLINE  |
+---------+

(Any state) ---decommission---> DECOMMISSIONED
```

### State Transitions in Detail

| From | To | Trigger |
|------|----|---------|
| (new) | PENDING | Node registered via `POST /api/nodes` |
| PENDING | ENROLLING | `POST /api/nodes/{id}/enroll` called. `DeploymentService.enroll_node()` sets status. |
| ENROLLING | ONLINE | Enrollment playbook succeeds. Agent starts heartbeating. `auth_method` set to `"key"`. |
| ENROLLING | ERROR | Enrollment playbook fails (SSH failure, missing deps, etc.). |
| ONLINE | DEGRADED | Optional role health check fails or heartbeat delayed but not expired. |
| ONLINE | OFFLINE | Heartbeat missed beyond `unhealthy_threshold` (3 missed = 90 seconds). Reconciler drives this. |
| ONLINE | MAINTENANCE | Admin sets maintenance mode via API. Suppresses alerts and auto-remediation. |
| DEGRADED | ONLINE | All health checks pass again on next heartbeat. |
| OFFLINE | ONLINE | Heartbeat resumes from node agent. |
| ERROR | PENDING | Admin resets node for re-enrollment. |
| MAINTENANCE | ONLINE | Admin exits maintenance mode. |
| (any) | DECOMMISSIONED | Admin decommissions node via `POST /api/nodes/{id}/decommission`. |

### Deployment Eligibility

Deployments (including Docker container deployments) can target nodes in the following states:

- **ONLINE** --- Standard target for deployments.
- **DEGRADED** --- Eligible for deployments that may fix the degradation.
- **MAINTENANCE** --- Eligible if the deployment is part of the maintenance operation.

Nodes in PENDING, ENROLLING, OFFLINE, ERROR, or DECOMMISSIONED states will reject deployment requests. The `DeploymentService` verifies the node exists but relies on the Ansible playbook to handle connectivity failures gracefully.

### Deployment Status Lifecycle

The `DeploymentStatus` enum tracks each deployment independently:

```
PENDING --> IN_PROGRESS --> COMPLETED
                       \-> FAILED --> (retry) --> PENDING (new deployment)
                       \-> CANCELLED

COMPLETED --> ROLLED_BACK (via rollback endpoint)
```

---

## 3. SLM Authentication

All SLM API endpoints (except `GET /api/health` and `GET /api/roles/definitions`) require a JWT Bearer token. The SLM uses HS256 JWT tokens with a 24-hour expiration by default.

### Authentication Flow

```
Client                          SLM Backend (/api/auth)
  |                                 |
  |  POST /api/auth/login           |
  |  {"username","password"}        |
  | ------------------------------> |
  |                                 |  verify credentials (bcrypt)
  |                                 |  create JWT (HS256, 24h TTL)
  |                                 |  record audit log entry
  |  {"access_token": "eyJ...",     |
  |   "token_type": "bearer",      |
  |   "expires_in": 86400}         |
  | <------------------------------ |
  |                                 |
  |  GET /api/nodes                 |
  |  Authorization: Bearer <token>  |
  | ------------------------------> |
  |                                 |  validate JWT (HS256)
  |                                 |  extract user from "sub" claim
  |  [nodes list]                   |
  | <------------------------------ |
```

### Python Authentication Client

```python
"""SLM Authentication Client.

Provides async helper functions for authenticating with the SLM
backend API and obtaining JWT Bearer tokens for subsequent requests.

The SLM backend runs behind nginx with self-signed TLS on the
internal 172.16.168.0/24 network. All examples use ssl=False
for self-signed certificate handling.
"""

import asyncio
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# SLM backend is behind nginx reverse proxy with TLS on port 443.
# Uvicorn binds to port 8000 internally (not exposed to LAN).
SLM_BASE_URL = "https://172.16.168.19"


async def authenticate(
    username: str = "admin",
    password: str = "",
    base_url: str = SLM_BASE_URL,
) -> str:
    """Authenticate with the SLM backend and return a JWT access token.

    Args:
        username: SLM admin username. Defaults to "admin".
        password: SLM admin password. Set via SLM_ADMIN_PASSWORD env var
            on the SLM server during deployment. On first startup without
            this env var, a random password is logged to stdout.
        base_url: SLM backend base URL. Defaults to the production
            nginx reverse proxy endpoint on port 443.

    Returns:
        JWT access token string for use in Authorization headers.

    Raises:
        aiohttp.ClientResponseError: If authentication fails (401) or
            the server returns an error status.
        aiohttp.ClientError: If the SLM server is unreachable.

    Example:
        >>> token = await authenticate(password="your_password")
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{base_url}/api/auth/login",
            json={"username": username, "password": password},
            ssl=False,  # Self-signed cert on internal network
        )
        response.raise_for_status()
        data = await response.json()
        logger.info(
            "Authenticated as %s (token expires in %ds)",
            username,
            data["expires_in"],
        )
        return data["access_token"]


async def get_authenticated_session(
    username: str = "admin",
    password: str = "",
    base_url: str = SLM_BASE_URL,
) -> tuple[aiohttp.ClientSession, dict]:
    """Create an authenticated aiohttp session with auth headers.

    Convenience function that authenticates and returns a session
    pre-configured with the Authorization header. The caller is
    responsible for closing the session.

    Args:
        username: SLM admin username.
        password: SLM admin password.
        base_url: SLM backend base URL.

    Returns:
        Tuple of (session, headers) where headers contains the
        Authorization Bearer token. Caller must close the session.

    Example:
        >>> session, headers = await get_authenticated_session(
        ...     password="your_password"
        ... )
        >>> try:
        ...     resp = await session.get(
        ...         f"{SLM_BASE_URL}/api/nodes",
        ...         headers=headers,
        ...         ssl=False,
        ...     )
        ...     nodes = await resp.json()
        ... finally:
        ...     await session.close()
    """
    token = await authenticate(username, password, base_url)
    headers = {"Authorization": f"Bearer {token}"}
    session = aiohttp.ClientSession()
    return session, headers


async def refresh_token(
    current_token: str,
    base_url: str = SLM_BASE_URL,
) -> str:
    """Refresh an existing JWT token before it expires.

    Args:
        current_token: The current valid JWT token.
        base_url: SLM backend base URL.

    Returns:
        New JWT access token string.

    Raises:
        aiohttp.ClientResponseError: If the current token is invalid
            or expired (401).
    """
    headers = {"Authorization": f"Bearer {current_token}"}
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{base_url}/api/auth/refresh",
            headers=headers,
            ssl=False,
        )
        response.raise_for_status()
        data = await response.json()
        return data["access_token"]
```

### Token Response Schema

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 86400
}
```

### Security Notes

- The SLM uses self-signed TLS certificates on the internal 172.16.168.0/24 network. Pass `ssl=False` (aiohttp) or `verify=False` (requests) when making API calls.
- The admin password is managed via the `SLM_ADMIN_PASSWORD` environment variable. When set, the SLM backend syncs the admin password on every startup (in `_ensure_admin_user()`), making the env var the single source of truth.
- Tokens expire after 24 hours (`access_token_expire_minutes = 60 * 24` in Settings).
- All authentication events (success and failure) are recorded in the `audit_logs` table with IP address, username, and timestamp.
- The JWT secret key comes from `SLM_SECRET_KEY`. If not set, a random key is generated on startup --- tokens will not survive restarts.

---

## 4. Creating an Ansible Playbook for Docker Deployment

Ansible playbooks for Docker deployment should be placed in the SLM Ansible directory at `/opt/autobot/autobot-slm-backend/ansible/` on the SLM server (172.16.168.19). The `PlaybookExecutor` resolves playbook names relative to this directory.

### Playbook: deploy-container.yml

```yaml
# deploy-container.yml
# Deploys a Docker container to target fleet nodes via AutoBot SLM.
#
# Usage via ansible-playbook CLI (from SLM server):
#   cd /opt/autobot/autobot-slm-backend/ansible
#   ansible-playbook -i inventory/slm-nodes.yml deploy-container.yml \
#     -e container_name=my-app \
#     -e container_image=nginx:latest \
#     -e container_port=8080 \
#     -e host_port=80 \
#     --limit 02-Frontend
#
# Usage via SLM API:
#   POST /api/infrastructure/execute
#   {"playbook_id": "deploy-container", "variables": {...}, "limit_hosts": [...]}
#
# Usage via PlaybookExecutor (Python):
#   executor = PlaybookExecutor()
#   result = await executor.execute_playbook(
#       "deploy-container.yml",
#       limit=["02-Frontend"],
#       extra_vars={"container_image": "nginx:latest"},
#   )
---
- name: Deploy Docker Container via AutoBot SLM
  hosts: "{{ target_hosts | default('docker_nodes') }}"
  become: true
  gather_facts: true

  vars:
    container_name: "{{ container_name | default('my-app') }}"
    container_image: "{{ container_image | default('nginx:latest') }}"
    container_port: "{{ container_port | default('8080') }}"
    host_port: "{{ host_port | default('80') }}"
    container_restart_policy: "{{ restart_policy | default('always') }}"
    container_memory_limit: "{{ memory_limit | default('512m') }}"
    data_volume_path: "{{ volume_path | default('/opt/autobot/data') }}"
    health_check_path: "{{ health_path | default('/health') }}"
    health_check_retries: "{{ health_retries | default(5) }}"

  tasks:
    # ==================================================================
    # Prerequisites: Docker Installation
    # ==================================================================
    - name: Ensure Docker prerequisites are installed
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
          - lsb-release
        state: present
        update_cache: true
      tags: [prerequisites]

    - name: Ensure Docker is installed
      apt:
        name: docker.io
        state: present
      tags: [prerequisites]

    - name: Ensure Docker service is running and enabled
      systemd:
        name: docker
        state: started
        enabled: true
      tags: [prerequisites]

    - name: Ensure autobot user is in docker group
      user:
        name: autobot
        groups: docker
        append: true
      tags: [prerequisites]

    - name: Install Docker SDK for Python (required for docker_* modules)
      pip:
        name: docker
        state: present
        executable: pip3
        extra_args: --break-system-packages
      tags: [prerequisites]

    # ==================================================================
    # Image Pull
    # ==================================================================
    - name: Pull Docker image
      docker_image:
        name: "{{ container_image }}"
        source: pull
        force_source: true
      register: image_pull_result
      tags: [deploy]

    - name: Log pulled image details
      debug:
        msg: >-
          Pulled {{ container_image }}
          (changed={{ image_pull_result.changed }})
      tags: [deploy]

    # ==================================================================
    # Container Deployment
    # ==================================================================
    - name: Stop existing container if running
      docker_container:
        name: "{{ container_name }}"
        state: absent
      ignore_errors: true
      tags: [deploy]

    - name: Ensure data volume directory exists
      file:
        path: "{{ data_volume_path }}"
        state: directory
        owner: autobot
        group: autobot
        mode: "0755"
      tags: [deploy]

    - name: Deploy Docker container
      docker_container:
        name: "{{ container_name }}"
        image: "{{ container_image }}"
        state: started
        restart_policy: "{{ container_restart_policy }}"
        ports:
          - "{{ host_port }}:{{ container_port }}"
        env:
          AUTOBOT_NODE: "{{ inventory_hostname }}"
          AUTOBOT_NODE_IP: "{{ ansible_host }}"
        volumes:
          - "{{ data_volume_path }}:/app/data"
        memory: "{{ container_memory_limit }}"
        log_driver: json-file
        log_options:
          max-size: "10m"
          max-file: "3"
      register: container_result
      tags: [deploy]

    # ==================================================================
    # Verification
    # ==================================================================
    - name: Verify container is running
      command: >-
        docker ps
        --filter name={{ container_name }}
        --format '{{ '{{' }}.Status{{ '}}' }}'
      register: container_status
      failed_when: "'Up' not in container_status.stdout"
      changed_when: false
      tags: [verify]

    - name: Display container status
      debug:
        msg: "Container {{ container_name }}: {{ container_status.stdout }}"
      tags: [verify]

    - name: Health check via HTTP
      uri:
        url: "http://localhost:{{ host_port }}{{ health_check_path }}"
        status_code: [200, 301, 302]
        timeout: 10
      retries: "{{ health_check_retries }}"
      delay: 3
      register: health_result
      ignore_errors: true
      tags: [verify]

    - name: Report health check result
      debug:
        msg: >-
          Health check {{ 'PASSED' if health_result is success else 'FAILED' }}
          for {{ container_name }} on port {{ host_port }}
      tags: [verify]

    # ==================================================================
    # Cleanup (tagged separately --- only runs with explicit --tags)
    # ==================================================================
    - name: Prune unused Docker images
      command: docker image prune -f
      changed_when: false
      tags: [cleanup, never]
```

### Playbook Design Principles

1. **Idempotent** --- Every task is safe to run multiple times. The `docker_container` module with `state: absent` followed by `state: started` ensures clean replacement.

2. **Parameterized** --- All deployment-specific values are passed as `extra_vars` from the SLM API (via `PlaybookExecutor`), with sensible defaults for standalone CLI use.

3. **Tagged** --- Tasks are grouped by phase (`prerequisites`, `deploy`, `verify`, `cleanup`) allowing selective execution via `--tags`.

4. **Verified** --- The playbook includes both container status checks (`docker ps`) and HTTP health checks (`uri` module) to confirm the deployment succeeded.

5. **Logged** --- Debug tasks output deployment details that appear in the `PlaybookExecutor` output stream and are stored in the deployment record's `playbook_output` field.

6. **Ownership-safe** --- Volume directories are created with explicit `owner: autobot` to avoid the root-ownership gotcha that occurs with `become: true`.

---

## 5. Deploying via the SLM API

The SLM provides three API paths for deploying Docker containers:

1. **Infrastructure Playbook Execution** (`POST /api/infrastructure/execute`) --- For registered infrastructure playbooks with the admin UI integration.
2. **Deployments API** (`POST /api/deployments`) --- For role-based deployments tracked in the deployments table.
3. **Role Migration** (`POST /api/roles/{role_name}/migrate`) --- For migrating a role to a different node via its configured `ansible_playbook`.

### Method A: Infrastructure Playbook Execution

This is the primary method for ad-hoc Docker deployments. The playbook must be registered in the `AVAILABLE_PLAYBOOKS` list in `autobot-slm-backend/api/infrastructure.py`.

```python
"""Deploy Docker containers via the SLM Infrastructure API.

Uses the /api/infrastructure/execute endpoint to run Ansible
playbooks registered in the SLM infrastructure playbook catalog.
The execution runs asynchronously and can be monitored via the
executions status endpoint.
"""

import asyncio
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

SLM_BASE_URL = "https://172.16.168.19"


async def deploy_docker_container(
    token: str,
    playbook_id: str = "deploy-container",
    container_image: str = "nginx:latest",
    container_name: str = "my-app",
    container_port: int = 8080,
    host_port: int = 80,
    target_hosts: Optional[list[str]] = None,
    base_url: str = SLM_BASE_URL,
) -> dict[str, Any]:
    """Deploy a Docker container to fleet nodes via SLM infrastructure API.

    This function submits an Ansible playbook execution request to the SLM
    backend and polls for completion. The playbook must be registered in
    the AVAILABLE_PLAYBOOKS list in api/infrastructure.py.

    The SLM backend creates a PlaybookExecution record, launches
    ansible-playbook as an async subprocess, and streams output to the
    execution log.

    Args:
        token: JWT access token from authenticate().
        playbook_id: ID of the registered infrastructure playbook.
            Must match a PlaybookInfo.id in AVAILABLE_PLAYBOOKS.
        container_image: Docker image to deploy (e.g., "nginx:latest",
            "redis:7-alpine").
        container_name: Name for the Docker container on the target host.
        container_port: Port the container listens on internally.
        host_port: Port to expose on the host machine.
        target_hosts: List of inventory hostnames to limit deployment to
            (e.g., ["02-Frontend", "03-AI-Stack"]). These must match
            host entries in inventory/slm-nodes.yml.
            If None, uses the playbook's default target_hosts.
        base_url: SLM backend base URL.

    Returns:
        Execution result dict with keys:
        - execution_id: Unique execution identifier
        - playbook_id: ID of the executed playbook
        - status: "completed", "failed", or "cancelled"
        - output: List of log lines from ansible-playbook
        - error: Error message if status is "failed"
        - started_at: ISO timestamp of execution start
        - completed_at: ISO timestamp of execution end
        - triggered_by: Username that initiated the deployment

    Raises:
        aiohttp.ClientResponseError: If the API returns 404 (playbook
            not found) or other error status.

    Example:
        >>> token = await authenticate(password="admin_password")
        >>> result = await deploy_docker_container(
        ...     token=token,
        ...     container_image="redis:7-alpine",
        ...     container_name="cache-server",
        ...     container_port=6379,
        ...     host_port=6380,
        ...     target_hosts=["03-AI-Stack"],
        ... )
        >>> print(f"Status: {result['status']}")
        Status: completed
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Submit playbook execution request
        execute_response = await session.post(
            f"{base_url}/api/infrastructure/execute",
            json={
                "playbook_id": playbook_id,
                "variables": {
                    "container_image": container_image,
                    "container_name": container_name,
                    "container_port": str(container_port),
                    "host_port": str(host_port),
                },
                "limit_hosts": target_hosts,
            },
            headers=headers,
            ssl=False,
        )
        execute_response.raise_for_status()
        execute_data = await execute_response.json()

        execution_id = execute_data["execution"]["execution_id"]
        logger.info(
            "Playbook execution started: %s (id=%s)",
            playbook_id,
            execution_id,
        )

        # Poll for completion
        result = await _poll_execution_status(
            session, execution_id, headers, base_url
        )
        return result


async def _poll_execution_status(
    session: aiohttp.ClientSession,
    execution_id: str,
    headers: dict,
    base_url: str,
    poll_interval: int = 5,
    timeout: int = 600,
) -> dict[str, Any]:
    """Poll an infrastructure playbook execution until completion.

    The SLM stores execution state in memory (dict keyed by execution_id).
    Status transitions: pending -> running -> completed/failed/cancelled.

    Args:
        session: Active aiohttp session.
        execution_id: The execution ID returned from the execute endpoint.
        headers: Authorization headers dict.
        base_url: SLM backend base URL.
        poll_interval: Seconds between status checks. Default 5.
        timeout: Maximum seconds to wait before giving up. Default 600.

    Returns:
        Final execution status dict from the SLM API.
    """
    elapsed = 0
    terminal_statuses = {"completed", "failed", "cancelled"}

    while elapsed < timeout:
        status_response = await session.get(
            f"{base_url}/api/infrastructure/executions/{execution_id}",
            headers=headers,
            ssl=False,
        )
        status_response.raise_for_status()
        status_data = await status_response.json()
        execution = status_data["execution"]

        current_status = execution["status"]
        logger.info(
            "Execution %s status: %s",
            execution_id,
            current_status,
        )

        if current_status in terminal_statuses:
            return execution

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.error("Execution %s timed out after %ds", execution_id, timeout)
    return {"execution_id": execution_id, "status": "timeout", "output": []}
```

### Method B: Deployments API

For deployments tied to specific roles, the SLM uses the `DeploymentService` which creates a persistent `Deployment` record in the database and executes the associated `deploy.yml` playbook:

```python
"""Deploy roles to nodes using the SLM Deployments API.

The Deployments API creates a deployment record in the PostgreSQL
database and executes the role's Ansible playbook asynchronously.
Deployments are fully tracked with lifecycle management (cancel,
rollback, retry).
"""

import asyncio
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

SLM_BASE_URL = "https://172.16.168.19"


async def deploy_via_deployment_api(
    token: str,
    node_id: str,
    roles: list[str],
    extra_data: Optional[dict] = None,
    base_url: str = SLM_BASE_URL,
) -> dict[str, Any]:
    """Create a deployment to a specific node via the SLM Deployments API.

    This uses the DeploymentService which runs the deploy.yml playbook
    against the target node with the specified roles. The deployment
    lifecycle is tracked in the deployments table:
    PENDING -> IN_PROGRESS -> COMPLETED/FAILED.

    Args:
        token: JWT access token.
        node_id: SLM node ID (e.g., "03-AI-Stack", "02-Frontend").
            Must match a node_id in the nodes table.
        roles: List of role names to deploy (e.g., ["backend", "redis"]).
            Must be valid role names from the AVAILABLE_ROLES list.
        extra_data: Optional metadata dict stored with the deployment
            record in the extra_data JSON column.
        base_url: SLM backend base URL.

    Returns:
        Deployment response dict with fields:
        - deployment_id: 8-char UUID
        - node_id: Target node
        - roles: Deployed role names
        - status: "pending", "in_progress", "completed", "failed",
          "cancelled", "rolled_back"
        - triggered_by: Username
        - created_at, started_at, completed_at: Timestamps

    Example:
        >>> token = await authenticate(password="admin_password")
        >>> result = await deploy_via_deployment_api(
        ...     token=token,
        ...     node_id="03-AI-Stack",
        ...     roles=["ai-stack"],
        ... )
        >>> print(f"Deployment {result['deployment_id']}: {result['status']}")
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Create the deployment
        response = await session.post(
            f"{base_url}/api/deployments",
            json={
                "node_id": node_id,
                "roles": roles,
                "extra_data": extra_data or {},
            },
            headers=headers,
            ssl=False,
        )
        response.raise_for_status()
        deployment = await response.json()

        deployment_id = deployment["deployment_id"]
        logger.info("Deployment created: %s", deployment_id)

        # Poll for completion
        result = await _poll_deployment_status(
            session, deployment_id, headers, base_url
        )
        return result


async def _poll_deployment_status(
    session: aiohttp.ClientSession,
    deployment_id: str,
    headers: dict,
    base_url: str,
    poll_interval: int = 5,
    timeout: int = 600,
) -> dict[str, Any]:
    """Poll a deployment until it reaches a terminal status.

    Args:
        session: Active aiohttp session.
        deployment_id: The deployment ID to monitor.
        headers: Authorization headers dict.
        base_url: SLM backend base URL.
        poll_interval: Seconds between status checks.
        timeout: Maximum seconds to wait.

    Returns:
        Final deployment status dict.
    """
    elapsed = 0
    terminal_statuses = {"completed", "failed", "cancelled", "rolled_back"}

    while elapsed < timeout:
        response = await session.get(
            f"{base_url}/api/deployments/{deployment_id}",
            headers=headers,
            ssl=False,
        )
        response.raise_for_status()
        deployment = await response.json()

        current_status = deployment["status"]
        logger.info("Deployment %s: %s", deployment_id, current_status)

        if current_status in terminal_statuses:
            return deployment

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.error(
        "Deployment %s timed out after %ds", deployment_id, timeout
    )
    return {"deployment_id": deployment_id, "status": "timeout"}
```

### Method C: Role Migration via PlaybookExecutor

```python
"""Migrate a role to a different node using the SLM Roles API.

This triggers the PlaybookExecutor to run the role's ansible_playbook
against the target node. The role must have an ansible_playbook field
configured in the roles database table.
"""

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

SLM_BASE_URL = "https://172.16.168.19"


async def migrate_role_to_node(
    token: str,
    role_name: str,
    target_node_id: str,
    base_url: str = SLM_BASE_URL,
) -> dict[str, Any]:
    """Migrate a role to a target node via Ansible playbook execution.

    Internally, the SLM Roles API calls PlaybookExecutor.execute_playbook()
    which builds and runs:
        ansible-playbook -i inventory/slm-nodes.yml <ansible_playbook>
            --limit <target_node_id>
            -e deploy_role=<role_name>

    Args:
        token: JWT access token.
        role_name: Name of the role to migrate (e.g., "backend", "redis").
        target_node_id: SLM node ID to deploy the role to (e.g.,
            "02-Frontend", "03-AI-Stack").
        base_url: SLM backend base URL.

    Returns:
        Migration result dict:
        - success: bool
        - role: Role name
        - target_node_id: Target node
        - playbook: Playbook filename used
        - output: Ansible output string
        - returncode: Process exit code (0 = success)

    Raises:
        aiohttp.ClientResponseError:
            404 if role not found.
            422 if role has no ansible_playbook configured.
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{base_url}/api/roles/{role_name}/migrate",
            json={"target_node_id": target_node_id},
            headers=headers,
            ssl=False,
        )
        response.raise_for_status()
        result = await response.json()

        logger.info(
            "Role migration %s -> %s: success=%s (rc=%d)",
            role_name,
            target_node_id,
            result["success"],
            result["returncode"],
        )
        return result
```

---

## 6. SLM API Endpoint Reference

All endpoints are prefixed with `/api` and require JWT Bearer authentication unless noted.

### Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `POST` | `/api/auth/login` | Authenticate, receive JWT token. Body: `{"username", "password"}`. | No |
| `POST` | `/api/auth/refresh` | Refresh an existing JWT token. | Yes |
| `GET` | `/api/auth/me` | Get current user info (`username`, `is_admin`). | Yes |
| `POST` | `/api/auth/users` | Create user (admin only). Body: `{"username", "password", "is_admin"}`. | Admin |

### Infrastructure Playbooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/infrastructure/playbooks` | List all registered infrastructure playbooks. Optional `?category=` filter (`database`, `monitoring`, `security`, `networking`, `storage`, `operations`). |
| `GET` | `/api/infrastructure/playbooks/{playbook_id}` | Get details of a specific playbook by ID. |
| `POST` | `/api/infrastructure/execute` | Execute a playbook. Body: `{"playbook_id", "variables", "limit_hosts"}`. Returns execution with `execution_id`. |
| `GET` | `/api/infrastructure/executions/{execution_id}` | Get execution status, output log, and timing. |
| `POST` | `/api/infrastructure/executions/{execution_id}/cancel` | Cancel a running or pending execution. |

### Deployments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/deployments` | List deployments. Filters: `?node_id=`, `?status=`, `?page=`, `?per_page=`. |
| `POST` | `/api/deployments` | Create a deployment. Body: `{"node_id", "roles", "extra_data"}`. Returns `deployment_id`. |
| `GET` | `/api/deployments/{deployment_id}` | Get deployment details including `playbook_output` and `error`. |
| `POST` | `/api/deployments/{deployment_id}/cancel` | Cancel a pending or in_progress deployment. |
| `POST` | `/api/deployments/{deployment_id}/rollback` | Rollback a completed deployment (removes roles from node). |
| `POST` | `/api/deployments/{deployment_id}/retry` | Retry a failed deployment (creates new deployment with same config). |

### Roles

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/roles` | List all role definitions (from `roles` table). |
| `GET` | `/api/roles/definitions` | Lightweight role definitions for agents (**no auth required**). |
| `GET` | `/api/roles/fleet-health` | Fleet health: `{"health": "healthy|degraded|critical", "required_down", "optional_down"}`. |
| `GET` | `/api/roles/owners` | Role-to-node ownership mapping (`{"owners": {"role": "node_id"}}`). |
| `GET` | `/api/roles/{role_name}` | Get specific role details including `ansible_playbook` field. |
| `POST` | `/api/roles` | Create a new role definition. |
| `PUT` | `/api/roles/{role_name}` | Update a role definition. |
| `DELETE` | `/api/roles/{role_name}` | Delete a role definition. |
| `POST` | `/api/roles/{role_name}/migrate` | Migrate role to a target node. Body: `{"target_node_id"}`. |
| `GET` | `/api/roles/node-actions/{node_id}` | Get available post-sync actions (build, restart, schema, install). |
| `POST` | `/api/roles/node-actions/{node_id}/execute` | Execute a post-sync action via SSH. Body: `{"role_name", "category"}`. |

### Nodes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/nodes` | List all managed nodes with status, health metrics, roles. |
| `POST` | `/api/nodes` | Register a new node. Body: `{"hostname", "ip_address", "ssh_user", "ssh_port"}`. |
| `GET` | `/api/nodes/{node_id}` | Get specific node details. |
| `PUT` | `/api/nodes/{node_id}` | Update node configuration. |
| `POST` | `/api/nodes/{node_id}/enroll` | Enroll a node (deploy SLM agent via Ansible). |
| `POST` | `/api/nodes/{node_id}/heartbeat` | Receive heartbeat from node agent (called by agent, not users). |
| `GET` | `/api/nodes/{node_id}/events` | Get node event history. |
| `POST` | `/api/nodes/{node_id}/decommission` | Decommission a node. |

### Code Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/code-sync/pull` | Pull latest code on SLM server from git. |
| `POST` | `/api/code-sync/fleet/sync` | Sync code to fleet nodes. Body: `{"strategy", "batch_size", "restart"}`. |
| `GET` | `/api/code-sync/fleet/sync/{job_id}` | Get fleet sync job status with per-node results. |

### Health

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/health` | Basic health check. | No |

### Deployment Roles (from `/api/deployments/roles`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/deployments/roles` | List available roles for deployment with UI metadata (category, tools, description). |

---

## 7. Inventory Configuration

The SLM uses Ansible inventory files to define fleet node targets. The `PlaybookExecutor` defaults to `{ansible_dir}/inventory/slm-nodes.yml`.

### Primary Inventory: slm-nodes.yml

This is the SLM-managed inventory used by the `PlaybookExecutor`. The full file is at `autobot-slm-backend/ansible/inventory/slm-nodes.yml`:

```yaml
# autobot-slm-backend/ansible/inventory/slm-nodes.yml
---
all:
  vars:
    ansible_user: autobot
    ansible_ssh_private_key_file: ~/.ssh/autobot_key
    ansible_python_interpreter: /usr/bin/python3

  children:
    slm_nodes:
      hosts:
        00-SLM-Manager:
          ansible_host: 172.16.168.19
          slm_node_id: "00-SLM-Manager"
        01-Backend:
          ansible_host: 172.16.168.20
          slm_node_id: "01-Backend"
        02-Frontend:
          ansible_host: 172.16.168.21
          slm_node_id: "02-Frontend"
        npu-worker:
          ansible_host: 172.16.168.22
          slm_node_id: "npu-worker"
        03-AI-Stack:
          ansible_host: 172.16.168.24
          slm_node_id: "03-AI-Stack"
        04-Databases:
          ansible_host: 172.16.168.23
          slm_node_id: "04-Databases"
        browser-automation:
          ansible_host: 172.16.168.25
          slm_node_id: "browser-automation"
        05-LLM-CPU:
          ansible_host: 172.16.168.26
          slm_node_id: "05-LLM-CPU"

    # Role-based groups for targeted deployments
    main:
      hosts:
        01-Backend:
    frontend:
      hosts:
        02-Frontend:
    npu_worker:
      hosts:
        npu-worker:
    redis:
      hosts:
        04-Databases:
    ai_stack:
      hosts:
        03-AI-Stack:
    browser_worker:
      hosts:
        browser-automation:
    llm_nodes:
      hosts:
        05-LLM-CPU:

    # Aggregate group for fleet-wide operations
    infrastructure:
      children:
        main:
        frontend:
        npu_worker:
        browser_worker:
        redis:
        ai_stack:
        slm_server:
        llm_nodes:
```

### Adding a Docker Nodes Group

To target nodes specifically for Docker container deployments, add a `docker_nodes` group to your inventory:

```yaml
    # Docker container deployment targets
    docker_nodes:
      hosts:
        02-Frontend:
        npu-worker:
        03-AI-Stack:
      vars:
        docker_data_dir: /opt/autobot/docker-data
        docker_log_driver: json-file
```

### Secondary Inventory: production.yml

The production inventory provides additional host variables (VM resources, service lists, port assignments) used by the `autobot-backend` Ansible playbooks. When running playbooks that need variables from both inventories, pass both `-i` flags:

```bash
# Both inventories required for full variable coverage
ansible-playbook \
  -i inventory/production.yml \
  -i inventory/slm-nodes.yml \
  deploy-container.yml
```

### Fleet Node Reference

| Inventory Host | IP Address | SLM Node ID | Role | Group(s) |
|----------------|------------|-------------|------|----------|
| `00-SLM-Manager` | 172.16.168.19 | `00-SLM-Manager` | SLM admin | `slm_server` |
| `01-Backend` | 172.16.168.20 | `01-Backend` | Main backend | `main` |
| `02-Frontend` | 172.16.168.21 | `02-Frontend` | User frontend | `frontend` |
| `npu-worker` | 172.16.168.22 | `npu-worker` | NPU acceleration | `npu_worker` |
| `04-Databases` | 172.16.168.23 | `04-Databases` | Redis Stack | `redis` |
| `03-AI-Stack` | 172.16.168.24 | `03-AI-Stack` | AI processing | `ai_stack` |
| `browser-automation` | 172.16.168.25 | `browser-automation` | Playwright | `browser_worker` |
| `05-LLM-CPU` | 172.16.168.26 | `05-LLM-CPU` | LLM inference | `llm_nodes` |

### Inventory Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ansible_user` | `autobot` | SSH username for all fleet nodes |
| `ansible_ssh_private_key_file` | `~/.ssh/autobot_key` | SSH private key path on SLM server |
| `ansible_python_interpreter` | `/usr/bin/python3` | Python interpreter on target nodes |
| `slm_node_id` | (per host) | Unique identifier matching the SLM database `nodes.node_id` |

---

## 8. Rolling Deployment Strategy

Rolling deployments update nodes one at a time (or in small batches) to maintain fleet availability. The SLM supports this through two mechanisms.

### A. Fleet Sync Rolling Deployment (Code + Restart)

The code sync API provides built-in rolling deployment with configurable batch sizes. This is the standard approach for updating code across the fleet:

```python
"""Rolling deployment using the SLM Fleet Sync API.

Syncs code and restarts services one node at a time to maintain
fleet availability during deployments. Uses the code-sync/fleet/sync
endpoint which handles git pull, rsync, and service restart.
"""

import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

SLM_BASE_URL = "https://172.16.168.19"


async def rolling_deploy_fleet_sync(
    token: str,
    batch_size: int = 1,
    restart: bool = True,
    strategy: str = "rolling",
    base_url: str = SLM_BASE_URL,
) -> dict[str, Any]:
    """Deploy code updates across the fleet with rolling strategy.

    Uses the SLM code sync API which handles:
    1. Git pull on SLM server (code_source)
    2. Rsync to each fleet node (one at a time)
    3. Service restart on each node (if restart=True)

    The fleet sync job is persisted to the fleet_sync_jobs table
    and survives backend restarts.

    Args:
        token: JWT access token.
        batch_size: Number of nodes to update simultaneously.
            IMPORTANT: Use batch_size=1 to avoid git index.lock
            race conditions. Parallel rsync on the same source repo
            can corrupt the git index.
        restart: Whether to restart services after sync.
        strategy: Deployment strategy ("rolling" or "parallel").
        base_url: SLM backend base URL.

    Returns:
        Fleet sync job status dict with per-node results:
        - job_id: Unique job identifier
        - status: "completed", "failed", or "partial"
        - total_nodes: Number of target nodes
        - completed_nodes: Successfully updated count
        - failed_nodes: Failed update count
        - nodes: Per-node status list

    Note:
        The batch_size=1 constraint exists because parallel rsync
        operations can cause git index.lock race conditions on the
        source repository. See CLAUDE.md Ansible Gotchas.
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Step 1: Pull latest code on SLM server
        pull_response = await session.post(
            f"{base_url}/api/code-sync/pull",
            headers=headers,
            ssl=False,
        )
        pull_response.raise_for_status()
        pull_data = await pull_response.json()
        logger.info("Code pull: %s", pull_data.get("message", "ok"))

        # Step 2: Start fleet sync with rolling strategy
        sync_response = await session.post(
            f"{base_url}/api/code-sync/fleet/sync",
            json={
                "strategy": strategy,
                "batch_size": batch_size,
                "restart": restart,
            },
            headers=headers,
            ssl=False,
        )
        sync_response.raise_for_status()
        sync_data = await sync_response.json()
        job_id = sync_data["job_id"]
        logger.info("Fleet sync started: job_id=%s", job_id)

        # Step 3: Poll for completion
        return await _poll_fleet_sync(session, job_id, headers, base_url)


async def _poll_fleet_sync(
    session: aiohttp.ClientSession,
    job_id: str,
    headers: dict,
    base_url: str,
    poll_interval: int = 5,
    timeout: int = 600,
) -> dict[str, Any]:
    """Poll fleet sync job until completion.

    Args:
        session: Active aiohttp session.
        job_id: Fleet sync job ID.
        headers: Authorization headers.
        base_url: SLM backend base URL.
        poll_interval: Seconds between polls.
        timeout: Maximum wait time in seconds.

    Returns:
        Final job status dict with per-node results.
    """
    elapsed = 0
    terminal_statuses = {"completed", "failed", "partial"}

    while elapsed < timeout:
        response = await session.get(
            f"{base_url}/api/code-sync/fleet/sync/{job_id}",
            headers=headers,
            ssl=False,
        )
        response.raise_for_status()
        job_status = await response.json()

        status = job_status.get("status", "unknown")
        completed = job_status.get("completed_nodes", 0)
        total = job_status.get("total_nodes", 0)
        logger.info(
            "Fleet sync %s: %s (%d/%d nodes)",
            job_id, status, completed, total,
        )

        if status in terminal_statuses:
            return job_status

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.error("Fleet sync %s timed out after %ds", job_id, timeout)
    return {"job_id": job_id, "status": "timeout"}
```

### B. Ansible Serial Strategy (Container-Specific)

For Docker container deployments specifically, use Ansible's built-in `serial` directive in the playbook to control the rollout rate:

```yaml
# deploy-container-rolling.yml
# Rolling Docker container deployment with health-gated progression.
# Each node is fully deployed and verified before proceeding to the next.
---
- name: Rolling Docker Container Deployment
  hosts: "{{ target_hosts | default('docker_nodes') }}"
  become: true
  serial: "{{ batch_size | default(1) }}"
  max_fail_percentage: 0

  vars:
    container_name: "{{ container_name | default('my-app') }}"
    container_image: "{{ container_image | default('nginx:latest') }}"
    container_port: "{{ container_port | default('8080') }}"
    host_port: "{{ host_port | default('80') }}"

  pre_tasks:
    - name: Pre-deployment health check
      uri:
        url: "http://localhost:{{ host_port }}/health"
        status_code: [200, 301, 302]
        timeout: 5
      ignore_errors: true
      register: pre_health

    - name: Record pre-deployment state
      debug:
        msg: >-
          Node {{ inventory_hostname }}:
          pre-deploy health={{ pre_health is success | default(false) }}

  tasks:
    - name: Pull new image
      docker_image:
        name: "{{ container_image }}"
        source: pull
        force_source: true

    - name: Replace container (recreate to apply changes)
      docker_container:
        name: "{{ container_name }}"
        image: "{{ container_image }}"
        state: started
        restart_policy: always
        recreate: true
        ports:
          - "{{ host_port }}:{{ container_port }}"
        env:
          AUTOBOT_NODE: "{{ inventory_hostname }}"
        volumes:
          - "/opt/autobot/data:/app/data"

    - name: Post-deployment health check
      uri:
        url: "http://localhost:{{ host_port }}/health"
        status_code: [200, 301, 302]
        timeout: 10
      retries: 5
      delay: 3
      register: post_health

    - name: Fail if health check does not pass
      fail:
        msg: >-
          Health check failed on {{ inventory_hostname }}
          after container deployment. Rolling deployment halted.
      when: post_health is failed
```

The `serial: 1` directive ensures Ansible completes all tasks on one host before moving to the next. Combined with `max_fail_percentage: 0`, a failure on any node halts the entire rollout, preventing cascading failures across the fleet.

---

## 9. Operational Gotchas

These are hard-won lessons from operating the AutoBot fleet. Violating these will cause deployment failures.

### Both Inventories Are Required

When running playbooks that reference production group vars, you need both inventory files:

```bash
# CORRECT
ansible-playbook \
  -i inventory/production.yml \
  -i inventory/slm-nodes.yml \
  deploy-container.yml

# WRONG - missing production vars (may work for simple playbooks)
ansible-playbook -i inventory/slm-nodes.yml deploy-container.yml
```

The `PlaybookExecutor` uses only `slm-nodes.yml` by default. If your playbook needs variables from `production.yml`, pass a custom `inventory_path` to `execute_playbook()`.

### All Builds Run FROM .19

The SLM server (172.16.168.19) is the Ansible controller. All `ansible-playbook` commands execute from .19. Never run Ansible from fleet nodes:

```bash
# CORRECT - run from SLM server
ssh autobot@172.16.168.19
cd /opt/autobot/autobot-slm-backend/ansible
ansible-playbook -i inventory/slm-nodes.yml deploy-container.yml

# WRONG - running Ansible from a fleet node
ssh autobot@172.16.168.24
ansible-playbook deploy-container.yml  # No inventory, no SSH keys
```

### Fleet Sync Batch Size Must Be 1

**Always use `batch_size=1` for fleet sync operations.** Parallel sync processes cause git `index.lock` race conditions on the source repository:

```python
# CORRECT
{"strategy": "rolling", "batch_size": 1, "restart": True}

# WRONG - causes index.lock race
{"strategy": "rolling", "batch_size": 3, "restart": True}
```

### Exclude venv When Syncing SLM Backend

**Always `--exclude='venv'` when syncing `autobot-slm-backend/` to .19.** Syncing the virtual environment breaks the Python runtime on the SLM server:

```bash
# CORRECT
rsync -avz --exclude='venv' autobot-slm-backend/ \
  autobot@172.16.168.19:/opt/autobot/autobot-slm-backend/

# WRONG - overwrites production venv
rsync -avz autobot-slm-backend/ \
  autobot@172.16.168.19:/opt/autobot/autobot-slm-backend/
```

### File Ownership After become: true

When Ansible tasks use `become: true`, created files are owned by root. Always add explicit ownership or use `become_user`:

```yaml
# WRONG - root owns the deployed files
- name: Deploy config
  copy:
    src: app.conf
    dest: /opt/autobot/config/app.conf
  become: true

# CORRECT - explicit ownership
- name: Deploy config
  copy:
    src: app.conf
    dest: /opt/autobot/config/app.conf
    owner: autobot
    group: autobot
    mode: "0644"
  become: true

# ALSO CORRECT - become_user
- name: Deploy config as autobot
  copy:
    src: app.conf
    dest: /opt/autobot/config/app.conf
  become: true
  become_user: autobot
```

### SSH Key Authentication

Fleet nodes use SSH key-based authentication (keys deployed during enrollment). The private key is at `~/.ssh/autobot_key` on the SLM server. Password authentication is only used during initial enrollment (via `sshpass`).

If SSH fails, check:
1. Key exists: `ls -la ~/.ssh/autobot_key`
2. Key works: `ssh -i ~/.ssh/autobot_key autobot@<target_ip> whoami`
3. Known issue: `.19` to `.24` SSH may fail because `/root/.ssh/autobot_key` is missing. Workaround: deploy manually via SSH from `.20`.

### No Direct Editing on VMs

All changes must follow the local-edit-then-sync pattern. See CLAUDE.md for details:

```bash
# CORRECT - edit locally, sync via Ansible
vim /home/kali/Desktop/AutoBot/autobot-slm-backend/ansible/deploy-container.yml
ansible-playbook ansible/playbooks/deploy-infrastructure.yml

# WRONG - direct editing on VM
ssh autobot@172.16.168.19 "vim /opt/autobot/.../deploy-container.yml"
```

### SLM Backend Startup Time

The SLM backend takes approximately 6 minutes to fully initialize (PostgreSQL migrations, role seeding, agent seeding, reconciler startup). HTTP 502 errors immediately after a restart are transient --- wait for the lifespan startup to complete before making API calls.

### Ansible Fact Cache Staleness

After OS upgrades on fleet nodes, clear the Ansible fact cache (24-hour TTL):

```bash
rm -f /tmp/ansible_fact_cache/<hostname>
```

Stale facts cause playbook failures from incorrect OS version detection.

### Migration Order Matters

When running database migrations: `db_service.initialize()` MUST run BEFORE incremental migrations. This is handled automatically by the SLM lifespan function but matters if you write custom setup scripts.

---

## 10. Complete End-to-End Example

This script demonstrates the full workflow: authenticate, verify fleet health, deploy a Docker container, and verify the deployment.

```python
#!/usr/bin/env python3
"""End-to-end Docker container deployment via AutoBot SLM.

This script demonstrates the complete workflow for deploying a Docker
container to AutoBot fleet nodes using the SLM API:

1. Authenticate with SLM backend
2. Check fleet health
3. List available nodes and verify targets are online
4. Deploy Docker container via Ansible playbook
5. Monitor deployment progress
6. Verify deployment success on each target node

Usage:
    export SLM_ADMIN_PASSWORD="your_password"
    python3 deploy_container.py

    # Custom deployment:
    export CONTAINER_IMAGE="redis:7-alpine"
    export CONTAINER_NAME="cache-server"
    export CONTAINER_PORT="6379"
    export HOST_PORT="6380"
    export TARGET_HOSTS="03-AI-Stack,npu-worker"
    python3 deploy_container.py

Requirements:
    pip install aiohttp
"""

import asyncio
import logging
import os
import sys

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("deploy-container")

SLM_BASE_URL = "https://172.16.168.19"


async def authenticate(
    password: str,
    base_url: str = SLM_BASE_URL,
) -> str:
    """Authenticate with SLM and return JWT token.

    Args:
        password: Admin password (from SLM_ADMIN_PASSWORD env var).
        base_url: SLM backend URL.

    Returns:
        JWT access token string.
    """
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{base_url}/api/auth/login",
            json={"username": "admin", "password": password},
            ssl=False,
        )
        if response.status == 401:
            logger.error("Authentication failed: invalid credentials")
            sys.exit(1)
        response.raise_for_status()
        data = await response.json()
        logger.info(
            "Authenticated (token expires in %ds)", data["expires_in"]
        )
        return data["access_token"]


async def check_fleet_health(
    session: aiohttp.ClientSession,
    headers: dict,
    base_url: str = SLM_BASE_URL,
) -> dict:
    """Check fleet health status before deployment.

    Args:
        session: Active aiohttp session.
        headers: Authorization headers.
        base_url: SLM backend URL.

    Returns:
        Fleet health dict: {"health", "required_down", "optional_down", "detail"}.
    """
    response = await session.get(
        f"{base_url}/api/roles/fleet-health",
        headers=headers,
        ssl=False,
    )
    response.raise_for_status()
    health = await response.json()
    logger.info("Fleet health: %s (%s)", health["health"], health["detail"])
    return health


async def list_online_nodes(
    session: aiohttp.ClientSession,
    headers: dict,
    base_url: str = SLM_BASE_URL,
) -> list:
    """List all nodes currently in ONLINE status.

    Args:
        session: Active aiohttp session.
        headers: Authorization headers.
        base_url: SLM backend URL.

    Returns:
        List of online node dicts with node_id, hostname, ip_address, status.
    """
    response = await session.get(
        f"{base_url}/api/nodes",
        headers=headers,
        ssl=False,
    )
    response.raise_for_status()
    data = await response.json()
    nodes = data.get("nodes", [])
    online = [n for n in nodes if n.get("status") == "online"]
    logger.info("Online nodes: %d/%d", len(online), len(nodes))
    for node in online:
        logger.info(
            "  %s (%s) - %s",
            node["node_id"],
            node["ip_address"],
            node.get("os_info", "unknown"),
        )
    return online


async def execute_docker_deployment(
    session: aiohttp.ClientSession,
    headers: dict,
    container_image: str,
    container_name: str,
    container_port: int,
    host_port: int,
    target_hosts: list[str],
    base_url: str = SLM_BASE_URL,
) -> dict:
    """Execute the Docker container deployment playbook.

    Submits a playbook execution request and polls until completion.

    Args:
        session: Active aiohttp session.
        headers: Authorization headers.
        container_image: Docker image to deploy.
        container_name: Container name.
        container_port: Internal container port.
        host_port: Host port to expose.
        target_hosts: Inventory hostnames to deploy to.
        base_url: SLM backend URL.

    Returns:
        Final execution status dict.
    """
    logger.info(
        "Deploying %s as '%s' (port %d:%d) to %s",
        container_image, container_name,
        host_port, container_port, target_hosts,
    )

    response = await session.post(
        f"{base_url}/api/infrastructure/execute",
        json={
            "playbook_id": "deploy-container",
            "variables": {
                "container_image": container_image,
                "container_name": container_name,
                "container_port": str(container_port),
                "host_port": str(host_port),
            },
            "limit_hosts": target_hosts,
        },
        headers=headers,
        ssl=False,
    )
    response.raise_for_status()
    data = await response.json()
    execution_id = data["execution"]["execution_id"]
    logger.info("Execution started: %s", execution_id)

    # Poll for completion (5s interval, 10min timeout)
    terminal_statuses = {"completed", "failed", "cancelled"}
    for poll in range(120):
        await asyncio.sleep(5)
        status_resp = await session.get(
            f"{base_url}/api/infrastructure/executions/{execution_id}",
            headers=headers,
            ssl=False,
        )
        status_resp.raise_for_status()
        execution = (await status_resp.json())["execution"]

        current_status = execution["status"]
        output_lines = execution.get("output", [])
        latest = output_lines[-1][:100] if output_lines else ""
        logger.info("[poll %d] %s - %s", poll + 1, current_status, latest)

        if current_status in terminal_statuses:
            return execution

    logger.error("Deployment timed out after 10 minutes")
    return {"status": "timeout", "execution_id": execution_id}


async def verify_deployment(
    session: aiohttp.ClientSession,
    target_node_ip: str,
    host_port: int,
    container_name: str,
) -> bool:
    """Verify the container is running and healthy on the target node.

    Args:
        session: Active aiohttp session.
        target_node_ip: IP address of the target node.
        host_port: Port the container is exposed on.
        container_name: Name of the deployed container.

    Returns:
        True if verification passes, False otherwise.
    """
    logger.info("Verifying deployment on %s:%d", target_node_ip, host_port)
    try:
        health_resp = await session.get(
            f"http://{target_node_ip}:{host_port}/health",
            timeout=aiohttp.ClientTimeout(total=10),
        )
        if health_resp.status in (200, 301, 302):
            logger.info("Health check PASSED: HTTP %d", health_resp.status)
            return True
        logger.warning("Health check returned HTTP %d", health_resp.status)
        return False
    except aiohttp.ClientError as e:
        logger.warning("Health check failed: %s", e)
        return False


async def main() -> int:
    """Main deployment workflow.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Configuration from environment
    password = os.getenv("SLM_ADMIN_PASSWORD", "")
    if not password:
        logger.error("SLM_ADMIN_PASSWORD not set. Export it first.")
        return 1

    container_image = os.getenv("CONTAINER_IMAGE", "nginx:latest")
    container_name = os.getenv("CONTAINER_NAME", "my-app")
    container_port = int(os.getenv("CONTAINER_PORT", "80"))
    host_port = int(os.getenv("HOST_PORT", "8080"))
    target_hosts = os.getenv("TARGET_HOSTS", "02-Frontend").split(",")

    # Step 1: Authenticate
    logger.info("=" * 60)
    logger.info("Step 1: Authenticating with SLM")
    logger.info("=" * 60)
    token = await authenticate(password)
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Step 2: Check fleet health
        logger.info("=" * 60)
        logger.info("Step 2: Checking fleet health")
        logger.info("=" * 60)
        health = await check_fleet_health(session, headers)
        if health["health"] == "critical":
            logger.error(
                "Fleet health is CRITICAL. Required roles offline: %s",
                health["required_down"],
            )
            return 1

        # Step 3: List online nodes
        logger.info("=" * 60)
        logger.info("Step 3: Listing online nodes")
        logger.info("=" * 60)
        online_nodes = await list_online_nodes(session, headers)
        online_ids = {n["node_id"] for n in online_nodes}
        offline_targets = [h for h in target_hosts if h not in online_ids]
        if offline_targets:
            logger.error(
                "Target hosts not online: %s. Available: %s",
                offline_targets, sorted(online_ids),
            )
            return 1

        # Step 4: Deploy container
        logger.info("=" * 60)
        logger.info("Step 4: Deploying Docker container")
        logger.info("=" * 60)
        result = await execute_docker_deployment(
            session, headers,
            container_image, container_name,
            container_port, host_port, target_hosts,
        )
        if result["status"] != "completed":
            logger.error("Deployment FAILED: %s", result["status"])
            if result.get("error"):
                logger.error("Error: %s", result["error"])
            for line in (result.get("output") or [])[-10:]:
                logger.error("  %s", line)
            return 1
        logger.info("Deployment completed successfully")

        # Step 5: Verify deployment
        logger.info("=" * 60)
        logger.info("Step 5: Verifying deployment")
        logger.info("=" * 60)
        node_ip_map = {n["node_id"]: n["ip_address"] for n in online_nodes}
        all_verified = True
        for host_id in target_hosts:
            target_ip = node_ip_map.get(host_id)
            if not target_ip:
                logger.warning("No IP found for %s", host_id)
                continue
            if not await verify_deployment(
                session, target_ip, host_port, container_name
            ):
                all_verified = False

        # Final status
        logger.info("=" * 60)
        if all_verified:
            logger.info("DEPLOYMENT SUCCESSFUL")
            logger.info(
                "Container '%s' running on %s (port %d)",
                container_name, target_hosts, host_port,
            )
            return 0
        logger.warning("DEPLOYMENT COMPLETED but verification FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

### Registering the Playbook in SLM

To make the Docker deployment playbook available via the SLM admin UI and API, add a `PlaybookInfo` entry to the `AVAILABLE_PLAYBOOKS` list in `autobot-slm-backend/api/infrastructure.py`:

```python
PlaybookInfo(
    id="deploy-container",
    name="Deploy Docker Container",
    description="Deploy a Docker container to target fleet nodes. "
        "Installs Docker if needed, pulls the image, deploys the "
        "container with configurable ports and volumes, and runs "
        "health verification.",
    category=PlaybookCategory.OPERATIONS,
    playbook_file="deploy-container.yml",
    target_hosts=["docker_nodes"],
    variables={
        "container_name": "my-app",
        "container_image": "nginx:latest",
        "container_port": "8080",
        "host_port": "80",
    },
    tags=["deploy", "docker"],
    estimated_duration="3-5 minutes",
    requires_confirmation=True,
),
```

---

## 11. Verification Checklist

After deploying a Docker container via SLM, verify every item in this checklist before considering the deployment complete.

### Container Verification (on target node)

```bash
# SSH to the target node
ssh autobot@<target_ip>

# 1. Container is running
docker ps --filter name=<container_name>
# Expected: STATUS shows "Up X minutes"

# 2. Container logs are clean
docker logs --tail 50 <container_name>
# Expected: No ERROR or FATAL messages in output

# 3. Container resource usage
docker stats --no-stream <container_name>
# Expected: CPU and memory within configured limits

# 4. Container port mapping
docker port <container_name>
# Expected: Shows correct mapping (e.g., 8080/tcp -> 0.0.0.0:80)
```

### Health Endpoint Verification

```bash
# 5. HTTP health check (from SLM server or any fleet node)
curl -s http://<target_ip>:<host_port>/health
# Expected: HTTP 200 with healthy response body

# 6. Fleet health via SLM API
curl -sk https://172.16.168.19/api/roles/fleet-health \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
# Expected: "health": "healthy" or "degraded" (not "critical")
```

### SLM State Verification

```bash
# 7. Deployment recorded and completed
curl -sk "https://172.16.168.19/api/deployments?node_id=<node_id>" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
# Expected: Latest deployment shows "status": "completed"

# 8. Node still online with recent heartbeat
curl -sk "https://172.16.168.19/api/nodes/<node_id>" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
# Expected: "status": "online", "last_heartbeat" within 60 seconds

# 9. Infrastructure execution log
curl -sk "https://172.16.168.19/api/infrastructure/executions/<execution_id>" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
# Expected: "status": "completed", output shows all tasks succeeded

# 10. No recent error events for the node
curl -sk "https://172.16.168.19/api/nodes/<node_id>/events" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
# Expected: No error or critical severity events in recent history
```

### Summary Table

| # | Check | Method | Expected Result |
|---|-------|--------|-----------------|
| 1 | Container running | `docker ps --filter name=<name>` | STATUS shows "Up" |
| 2 | Logs clean | `docker logs --tail 50 <name>` | No errors |
| 3 | Resource usage | `docker stats --no-stream <name>` | Within limits |
| 4 | Port mapping | `docker port <name>` | Correct host:container mapping |
| 5 | Health endpoint | `curl http://<ip>:<port>/health` | HTTP 200 |
| 6 | Fleet health | `GET /api/roles/fleet-health` | `"healthy"` or `"degraded"` |
| 7 | Deployment record | `GET /api/deployments?node_id=<id>` | `"status": "completed"` |
| 8 | Node online | `GET /api/nodes/<id>` | `"status": "online"` |
| 9 | Execution log | `GET /api/infrastructure/executions/<id>` | `"status": "completed"` |
| 10 | No error events | `GET /api/nodes/<id>/events` | No recent errors |

---

## Related Documentation

- [CLAUDE.md](../../CLAUDE.md) --- Development rules, deployment workflow, local-edit-then-sync policy
- [AUTOBOT_REFERENCE.md](../developer/AUTOBOT_REFERENCE.md) --- Infrastructure IPs, service layout, sync commands
- [ANSIBLE_PLAYBOOK_REFERENCE.md](ANSIBLE_PLAYBOOK_REFERENCE.md) --- Existing Ansible playbook catalog
- [SLM Backend Source](../../autobot-slm-backend/) --- Source code for all APIs referenced in this guide
- [SLM Inventory](../../autobot-slm-backend/ansible/inventory/) --- Ansible inventory files
