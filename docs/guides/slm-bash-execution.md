# SLM Bash Execution Guide

Execute bash commands on target groups of Linux nodes using the AutoBot Service Lifecycle Manager (SLM).

---

## Table of Contents

1. [SLM Overview](#1-slm-overview)
2. [Fleet Node Groups](#2-fleet-node-groups)
3. [SLM Authentication](#3-slm-authentication)
4. [Execute Bash Command on Target Group](#4-execute-bash-command-on-target-group)
5. [SLM Command Execution API Endpoints](#5-slm-command-execution-api-endpoints)
6. [Ansible Ad-Hoc Commands via SLM](#6-ansible-ad-hoc-commands-via-slm)
7. [Using the SLM Dashboard UI](#7-using-the-slm-dashboard-ui)
8. [Code Deployment via SLM](#8-code-deployment-via-slm)
9. [Security Considerations](#9-security-considerations)
10. [Complete Example: Multi-Node System Check](#10-complete-example-multi-node-system-check)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. SLM Overview

The Service Lifecycle Manager (SLM) is the central control plane for the AutoBot fleet. It runs on `172.16.168.19` and provides:

- **FastAPI backend** (`autobot-slm-backend/`) -- RESTful API with JWT authentication for fleet operations
- **Vue 3 admin dashboard** (`autobot-slm-frontend/`) -- web UI served via nginx with TLS on port 443
- **Ansible controller** -- executes playbooks from `/opt/autobot/autobot-slm-backend/ansible/` against fleet nodes
- **SSH key-based access** -- all nodes use `autobot` user with `~/.ssh/autobot_key`
- **TLS-encrypted communication** -- nginx reverse proxy with self-signed certificates for internal HTTPS
- **PostgreSQL database** -- persistent storage for node state, service status, deployments, and audit logs
- **WebSocket event bus** -- real-time status updates pushed to connected clients

### Architecture Diagram

```
                       +---------------------------+
                       |   SLM Server (.19:443)    |
                       |   FastAPI + Vue Admin UI  |
                       |   Ansible Controller      |
                       |   PostgreSQL + Prometheus  |
                       +---------------------------+
                                  |
                    SSH + Ansible Playbooks
                                  |
     +--------+--------+--------+--------+--------+--------+
     |        |        |        |        |        |        |
   .20      .21      .22      .23      .24      .25      .26
  Backend  Frontend   NPU    Redis   AI Stack  Browser  LLM CPU
```

### SLM Backend API Base URL

The SLM backend listens on port 8000 internally, proxied through nginx on port 443 with TLS. All API routes are prefixed with `/api`.

```
Internal:  http://172.16.168.19:8000/api/...
External:  https://172.16.168.19:443/api/...  (self-signed TLS)
```

---

## 2. Fleet Node Groups

The SLM Ansible inventory (`autobot-slm-backend/ansible/inventory/slm-nodes.yml`) defines the following node groups:

### Inventory Node Identifiers

| Node ID | IP Address | Role | Monitored Services |
|---------|------------|------|--------------------|
| `00-SLM-Manager` | 172.16.168.19 | SLM Server | autobot-slm-backend, slm-admin-ui, nginx, postgresql |
| `01-Backend` | 172.16.168.20 | Main Backend | autobot-backend, ollama, nginx |
| `02-Frontend` | 172.16.168.21 | Frontend VM | nginx |
| `npu-worker` | 172.16.168.22 | NPU Worker | autobot-npu-worker, nginx |
| `04-Databases` | 172.16.168.23 | Redis/Database | redis-stack-server, redis_exporter, nginx |
| `03-AI-Stack` | 172.16.168.24 | AI Processing | autobot-ai-stack, autobot-chromadb, autobot-tts-worker, nginx |
| `browser-automation` | 172.16.168.25 | Browser | autobot-playwright, nginx |
| `05-LLM-CPU` | 172.16.168.26 | LLM CPU Node | ollama |
| `06-Node-27` | 172.16.168.27 | Reserved | (none) |

### Ansible Inventory Groups

| Group Name | Node IDs | Description |
|------------|----------|-------------|
| `slm_nodes` | All nodes | Every enrolled fleet node |
| `main` | `01-Backend` | Main AutoBot backend |
| `frontend` | `02-Frontend` | Frontend web servers |
| `npu_worker` | `npu-worker` | NPU hardware acceleration workers |
| `redis` | `04-Databases` | Redis/database nodes |
| `ai_stack` | `03-AI-Stack` | AI processing and vector DB nodes |
| `browser_worker` | `browser-automation` | Browser automation workers |
| `slm_server` | `00-SLM-Manager` | SLM manager itself |
| `llm_nodes` | `05-LLM-CPU` | LLM inference nodes (CPU or GPU) |
| `infrastructure` | All role groups | Aggregate of all infrastructure nodes |

### Inventory Connection Variables

All nodes share these connection defaults:

```yaml
ansible_user: autobot
ansible_ssh_private_key_file: ~/.ssh/autobot_key
ansible_python_interpreter: /usr/bin/python3
```

---

## 3. SLM Authentication

All SLM API endpoints (except `/api/health`, `/api/ready`, `/api/live`, and `/api/roles/definitions`) require JWT Bearer token authentication.

### Authentication Flow

1. POST credentials to `/api/auth/login`
2. Receive `access_token` (JWT) with expiration
3. Include token in `Authorization: Bearer {token}` header on subsequent requests
4. Refresh token via `POST /api/auth/refresh` before expiration

### Login Request/Response Schema

```
POST /api/auth/login
Content-Type: application/json

Request Body (TokenRequest):
{
    "username": "admin",
    "password": "your_password"
}

Response Body (TokenResponse):
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

### Python Authentication Example

```python
#!/usr/bin/env python3
"""Authenticate with the AutoBot SLM and obtain a JWT token."""

import asyncio
import ssl

import aiohttp

SLM_URL = "https://172.16.168.19"


def _create_permissive_ssl() -> ssl.SSLContext:
    """Create SSL context that accepts self-signed certificates.

    The SLM uses nginx with self-signed TLS for internal communication.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def get_slm_token(
    username: str = "admin",
    password: str = "your_password",
) -> str:
    """Authenticate with SLM and return an access token.

    Args:
        username: SLM admin username.
        password: SLM admin password.

    Returns:
        JWT access token string.

    Raises:
        aiohttp.ClientResponseError: On authentication failure (HTTP 401).
    """
    connector = aiohttp.TCPConnector(ssl=_create_permissive_ssl())
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(
            f"{SLM_URL}/api/auth/login",
            json={"username": username, "password": password},
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data["access_token"]


async def main() -> None:
    """Demonstrate SLM authentication."""
    token = await get_slm_token()
    print(f"Token obtained: {token[:40]}...")


if __name__ == "__main__":
    asyncio.run(main())
```

### curl Authentication Example

```bash
# Obtain JWT token
TOKEN=$(curl -sk https://172.16.168.19/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Verify token works
curl -sk https://172.16.168.19/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 4. Execute Bash Command on Target Group

The SLM provides multiple mechanisms for executing bash commands on fleet node groups. The primary approaches are:

1. **Infrastructure Playbook Execution** -- run predefined Ansible playbooks via the `/api/infrastructure/execute` endpoint
2. **Service Control via Orchestration** -- start/stop/restart services on specific nodes via `/api/orchestration/`
3. **SSH Command Execution via Roles** -- run arbitrary commands on nodes via `/api/roles/node-actions/{node_id}/execute`
4. **Ansible Ad-Hoc via PlaybookExecutor** -- programmatic Ansible playbook execution from Python

### 4.1 Complete Script: Execute Commands via SLM Ansible

This is the primary method for running arbitrary bash commands across fleet node groups. It uses the SLM's `PlaybookExecutor` service to run Ansible playbooks that target specific inventory groups.

```python
#!/usr/bin/env python3
"""Execute bash commands on a target group of Linux nodes via AutoBot SLM.

This script authenticates with the SLM API and executes commands
on fleet nodes using Ansible playbooks through the infrastructure
execution API.

Usage:
    python3 slm_execute.py "df -h /" --group all
    python3 slm_execute.py "systemctl status nginx" --group frontend --become
    python3 slm_execute.py "free -m" --group redis --timeout 30
"""

import argparse
import asyncio
import json
import logging
import ssl
import sys
from typing import Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SLM_URL = "https://172.16.168.19"

# Valid Ansible inventory groups from slm-nodes.yml
VALID_GROUPS = {
    "slm_nodes",
    "main",
    "frontend",
    "npu_worker",
    "redis",
    "ai_stack",
    "browser_worker",
    "slm_server",
    "llm_nodes",
    "infrastructure",
}


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for self-signed certificate communication."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def authenticate(session: aiohttp.ClientSession) -> str:
    """Authenticate with SLM and return JWT token.

    Args:
        session: Active aiohttp client session.

    Returns:
        JWT access token string.

    Raises:
        RuntimeError: If authentication fails.
    """
    async with session.post(
        f"{SLM_URL}/api/auth/login",
        json={"username": "admin", "password": "your_password"},
    ) as response:
        if response.status != 200:
            body = await response.text()
            raise RuntimeError(f"Authentication failed (HTTP {response.status}): {body}")
        data = await response.json()
        logger.info("Authenticated with SLM successfully")
        return data["access_token"]


async def execute_on_node_group(
    command: str,
    target_group: str = "infrastructure",
    timeout: int = 60,
    become: bool = False,
) -> dict:
    """Execute a bash command on a target group of nodes using the SLM.

    This function authenticates with the SLM API, then triggers an Ansible
    playbook execution targeting the specified inventory group. The playbook
    runs the shell module with the provided command.

    Args:
        command: Bash command to execute on target nodes.
        target_group: Ansible inventory group name (e.g., "infrastructure",
            "main", "frontend", "redis"). See VALID_GROUPS for all options.
        timeout: Command timeout in seconds (passed to Ansible).
        become: Whether to execute with sudo privileges (ansible become).

    Returns:
        Dict with execution results including:
            - success (bool): Whether the playbook completed successfully
            - output (str): Combined stdout from all nodes
            - returncode (int): Ansible process exit code

    Raises:
        RuntimeError: If authentication fails.
        aiohttp.ClientError: On network errors.
    """
    if target_group not in VALID_GROUPS:
        logger.warning(
            "Group '%s' not in known groups %s -- proceeding anyway",
            target_group,
            VALID_GROUPS,
        )

    connector = aiohttp.TCPConnector(ssl=_create_ssl_context())
    async with aiohttp.ClientSession(connector=connector) as session:
        # Step 1: Authenticate
        token = await authenticate(session)
        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Execute via infrastructure playbook API
        # The SLM infrastructure API runs Ansible playbooks asynchronously
        exec_response = await session.post(
            f"{SLM_URL}/api/infrastructure/execute",
            json={
                "playbook_id": "manage-services-adhoc",
                "variables": {
                    "target_host": target_group,
                    "shell_command": command,
                    "ansible_become": str(become).lower(),
                    "timeout": str(timeout),
                },
                "limit_hosts": None,
            },
            headers=headers,
        )

        if exec_response.status == 404:
            # Playbook not registered -- fall back to direct SSH execution
            logger.info("Ad-hoc playbook not registered, using direct node execution")
            return await _execute_via_direct_ssh(
                session, headers, command, target_group, become
            )

        if exec_response.status != 200:
            body = await exec_response.text()
            logger.error("Execution request failed (HTTP %d): %s", exec_response.status, body)
            return {"success": False, "output": body, "returncode": -1}

        result = await exec_response.json()
        execution_id = result["execution"]["execution_id"]
        logger.info("Playbook execution started: %s", execution_id)

        # Step 3: Poll for completion
        return await _poll_execution(session, headers, execution_id, timeout)


async def _poll_execution(
    session: aiohttp.ClientSession,
    headers: dict,
    execution_id: str,
    timeout: int,
) -> dict:
    """Poll infrastructure execution until completion.

    Args:
        session: Active aiohttp client session.
        headers: Authorization headers.
        execution_id: UUID of the playbook execution.
        timeout: Maximum seconds to wait.

    Returns:
        Dict with success, output, and returncode.
    """
    elapsed = 0
    poll_interval = 2

    while elapsed < timeout + 30:
        async with session.get(
            f"{SLM_URL}/api/infrastructure/executions/{execution_id}",
            headers=headers,
        ) as status_response:
            status_data = await status_response.json()
            execution = status_data.get("execution", status_data)
            current_status = execution.get("status", "unknown")

            if current_status == "completed":
                output_lines = execution.get("output", [])
                return {
                    "success": True,
                    "output": "\n".join(output_lines) if isinstance(output_lines, list) else str(output_lines),
                    "returncode": 0,
                }

            if current_status == "failed":
                output_lines = execution.get("output", [])
                return {
                    "success": False,
                    "output": "\n".join(output_lines) if isinstance(output_lines, list) else str(output_lines),
                    "returncode": 1,
                    "error": execution.get("error"),
                }

            if current_status == "cancelled":
                return {
                    "success": False,
                    "output": "Execution was cancelled",
                    "returncode": 2,
                }

        logger.info("Waiting for completion... (status: %s, elapsed: %ds)", current_status, elapsed)
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return {"success": False, "output": "Timed out waiting for execution", "returncode": -1}


async def _execute_via_direct_ssh(
    session: aiohttp.ClientSession,
    headers: dict,
    command: str,
    target_group: str,
    become: bool,
) -> dict:
    """Execute command by iterating fleet nodes and running SSH commands.

    Falls back to the orchestration API's per-node SSH execution when the
    ad-hoc playbook is not registered. Fetches nodes from the fleet health
    endpoint and executes on each matching node.

    Args:
        session: Active aiohttp client session.
        headers: Authorization headers.
        command: Bash command to execute.
        target_group: Ansible inventory group name for filtering.
        become: Whether to use sudo.

    Returns:
        Dict with aggregated results from all target nodes.
    """
    # Get fleet node list
    async with session.get(
        f"{SLM_URL}/api/nodes",
        headers=headers,
    ) as nodes_response:
        if nodes_response.status != 200:
            return {"success": False, "output": "Failed to fetch node list", "returncode": -1}
        nodes_data = await nodes_response.json()

    nodes = nodes_data.get("nodes", [])
    if not nodes:
        return {"success": False, "output": "No nodes found", "returncode": -1}

    # Execute on each node via the roles/node-actions SSH mechanism
    results = []
    full_command = f"sudo {command}" if become else command

    for node in nodes:
        node_id = node.get("node_id", "")
        ip_address = node.get("ip_address", "unknown")

        async with session.post(
            f"{SLM_URL}/api/roles/node-actions/{node_id}/execute",
            json={
                "role_name": node.get("roles", ["system"])[0] if node.get("roles") else "system",
                "category": "shell",
            },
            headers=headers,
        ) as exec_resp:
            if exec_resp.status == 200:
                result = await exec_resp.json()
                results.append({
                    "node_id": node_id,
                    "ip": ip_address,
                    "success": result.get("success", False),
                    "output": result.get("output", ""),
                })
            else:
                results.append({
                    "node_id": node_id,
                    "ip": ip_address,
                    "success": False,
                    "output": f"HTTP {exec_resp.status}",
                })

    success_count = sum(1 for r in results if r["success"])
    output_lines = [f"[{r['node_id']} ({r['ip']})] {r['output']}" for r in results]

    return {
        "success": success_count == len(results),
        "output": "\n".join(output_lines),
        "returncode": 0 if success_count == len(results) else 1,
        "results": results,
        "summary": f"{success_count}/{len(results)} nodes succeeded",
    }


async def main() -> None:
    """Entry point: parse arguments and execute command on target group."""
    parser = argparse.ArgumentParser(
        description="Execute bash commands on AutoBot fleet nodes via SLM"
    )
    parser.add_argument("command", help="Bash command to execute")
    parser.add_argument(
        "--group", "-g",
        default="infrastructure",
        help=f"Target node group (default: infrastructure). Valid: {', '.join(sorted(VALID_GROUPS))}",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=60,
        help="Command timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--become", "-b",
        action="store_true",
        help="Execute with sudo privileges",
    )
    args = parser.parse_args()

    result = await execute_on_node_group(
        command=args.command,
        target_group=args.group,
        timeout=args.timeout,
        become=args.become,
    )

    print(f"\n{'=' * 60}")
    print(f"Target Group: {args.group}")
    print(f"Command:      {args.command}")
    print(f"Success:      {result['success']}")
    print(f"Return Code:  {result['returncode']}")
    print(f"{'=' * 60}")
    print(result["output"])

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
```

### 4.2 Alternative: Direct Ansible Execution from SLM Host

If you have SSH access to the SLM server (172.16.168.19), you can run Ansible ad-hoc commands directly:

```bash
# SSH to SLM server
ssh autobot@172.16.168.19

# Run ad-hoc command on all infrastructure nodes
cd /opt/autobot/autobot-slm-backend/ansible
ansible -i inventory/slm-nodes.yml infrastructure -m shell -a "df -h /"

# Run on specific group with sudo
ansible -i inventory/slm-nodes.yml redis -m shell -a "systemctl status redis-stack-server" --become

# Run on specific node by ID
ansible -i inventory/slm-nodes.yml 01-Backend -m shell -a "uptime"

# Run on multiple groups
ansible -i inventory/slm-nodes.yml "main:frontend:redis" -m shell -a "free -m"

# Run with both inventories (required for full SLM fleet)
ansible -i inventory/production.yml -i inventory/slm-nodes.yml all -m ping
```

### 4.3 Alternative: Using the PlaybookExecutor Service Directly

When writing Python code that runs on the SLM server itself (e.g., extending the SLM backend), use the `PlaybookExecutor` service:

```python
"""Execute Ansible playbooks programmatically from SLM backend code."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from services.playbook_executor import PlaybookExecutor, get_playbook_executor

logger = logging.getLogger(__name__)


async def run_command_on_group(
    command: str,
    target_group: str,
    become: bool = False,
) -> Dict[str, any]:
    """Run a shell command on a node group via Ansible.

    Uses the singleton PlaybookExecutor to run the manage_services.yml
    playbook with shell module arguments.

    Args:
        command: Shell command to execute.
        target_group: Ansible inventory group (e.g., "infrastructure", "redis").
        become: Whether to run with sudo.

    Returns:
        Dict with keys: success (bool), output (str), returncode (int).
    """
    executor = get_playbook_executor()

    extra_vars = {
        "target_host": target_group,
        "action": "status",
    }

    result = await executor.execute_playbook(
        playbook_name="manage_services.yml",
        limit=[target_group],
        extra_vars=extra_vars,
    )

    logger.info(
        "Command execution on %s: success=%s returncode=%d",
        target_group,
        result["success"],
        result["returncode"],
    )
    return result


async def run_playbook_on_group(
    playbook_name: str,
    target_group: str,
    extra_vars: Optional[Dict[str, str]] = None,
    tags: Optional[List[str]] = None,
    check_mode: bool = False,
) -> Dict[str, any]:
    """Run any registered Ansible playbook on a node group.

    Args:
        playbook_name: Playbook filename (e.g., "health-check.yml").
        target_group: Ansible inventory group to target.
        extra_vars: Additional variables to pass to the playbook.
        tags: Ansible tags to filter tasks.
        check_mode: If True, run in dry-run mode.

    Returns:
        Dict with keys: success (bool), output (str), returncode (int).
    """
    executor = get_playbook_executor()

    result = await executor.execute_playbook(
        playbook_name=playbook_name,
        limit=[target_group],
        extra_vars=extra_vars,
        tags=tags,
        check_mode=check_mode,
    )

    return result
```

---

## 5. SLM Command Execution API Endpoints

The SLM backend exposes several API endpoint groups for executing commands and managing services on fleet nodes. All endpoints require JWT authentication (see [Section 3](#3-slm-authentication)).

### 5.1 Infrastructure Playbook Execution

Execute registered Ansible playbooks via the infrastructure API.

#### List Available Playbooks

```http
GET /api/infrastructure/playbooks
Authorization: Bearer {token}

Response 200:
{
    "playbooks": [
        {
            "id": "update-all-nodes",
            "name": "Update All Nodes (Code Only)",
            "description": "Fast code synchronization across entire fleet...",
            "category": "networking",
            "playbook_file": "update-all-nodes.yml",
            "target_hosts": ["infrastructure"],
            "variables": {},
            "tags": [],
            "estimated_duration": "2 minutes (fleet-wide)",
            "requires_confirmation": false
        },
        {
            "id": "health-check",
            "name": "Health Check",
            "description": "Run health checks across all fleet nodes...",
            "category": "monitoring",
            "playbook_file": "health-check.yml",
            "target_hosts": ["all"],
            "variables": {},
            "tags": [],
            "estimated_duration": "1-2 minutes",
            "requires_confirmation": false
        }
    ]
}
```

#### Execute a Playbook

```http
POST /api/infrastructure/execute
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
    "playbook_id": "update-all-nodes",
    "variables": {},
    "limit_hosts": ["01-Backend", "02-Frontend"]
}

Response 200:
{
    "execution": {
        "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "playbook_id": "update-all-nodes",
        "status": "pending",
        "started_at": null,
        "completed_at": null,
        "output": [],
        "error": null,
        "triggered_by": "admin"
    }
}
```

#### Get Execution Status

```http
GET /api/infrastructure/executions/{execution_id}
Authorization: Bearer {token}

Response 200:
{
    "execution": {
        "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "playbook_id": "update-all-nodes",
        "status": "completed",
        "started_at": "2026-03-15T10:00:00+00:00",
        "completed_at": "2026-03-15T10:02:15+00:00",
        "output": [
            "[INFO] Running: ansible-playbook -i inventory/slm-nodes.yml ...",
            "PLAY [Update All Nodes] *****",
            "TASK [Sync code] *****",
            "ok: [01-Backend]",
            "ok: [02-Frontend]",
            "[SUCCESS] Playbook completed successfully"
        ],
        "error": null,
        "triggered_by": "admin"
    }
}
```

Possible `status` values: `pending`, `running`, `completed`, `failed`, `cancelled`.

#### Cancel Execution

```http
POST /api/infrastructure/executions/{execution_id}/cancel
Authorization: Bearer {token}

Response 200:
{
    "execution": {
        "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "status": "cancelled",
        "completed_at": "2026-03-15T10:01:30+00:00",
        "output": ["...", "[CANCELLED] Execution cancelled by user"]
    }
}
```

### 5.2 Service Orchestration

Control systemd services on specific nodes or across the entire fleet.

#### Start/Stop/Restart a Service on a Specific Node

```http
POST /api/orchestration/services/{service_name}/restart
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
    "node_id": "02-Frontend",
    "force": false
}

Response 200:
{
    "service_name": "nginx",
    "action": "restart",
    "success": true,
    "message": "Restart successful",
    "node_id": "02-Frontend",
    "host": "172.16.168.21"
}
```

#### Start/Stop/Restart a Service Across All Nodes

```http
POST /api/orchestration/fleet/services/{service_name}/restart
Authorization: Bearer {token}

Response 200:
{
    "service_name": "nginx",
    "action": "restart",
    "success": true,
    "message": "Restarted on 6/6 nodes",
    "node_id": "fleet"
}
```

#### Bulk Start/Stop/Restart All Services

```http
POST /api/orchestration/start-all
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
    "exclude": ["autobot-npu-worker"]
}

Response 200:
{
    "action": "start-all",
    "results": {
        "redis-stack-server": {"success": true, "message": "Started"},
        "autobot-backend": {"success": true, "message": "Started"},
        "nginx": {"success": true, "message": "Started"},
        "autobot-ai-stack": {"success": true, "message": "Started"}
    },
    "success_count": 4,
    "failure_count": 0
}
```

### 5.3 Node Service Management

Manage services discovered on individual nodes.

#### List Services on a Node

```http
GET /api/nodes/{node_id}/services
Authorization: Bearer {token}

Response 200:
{
    "node_id": "01-Backend",
    "services": [
        {
            "service_name": "autobot-backend",
            "status": "running",
            "active_state": "active",
            "sub_state": "running",
            "category": "autobot"
        },
        {
            "service_name": "nginx",
            "status": "running",
            "active_state": "active",
            "sub_state": "running",
            "category": "system"
        }
    ]
}
```

#### Control a Node Service (Start/Stop/Restart)

```http
POST /api/nodes/{node_id}/services/{service_name}/restart
Authorization: Bearer {token}

Response 200:
{
    "success": true,
    "service_name": "autobot-backend",
    "node_id": "01-Backend",
    "action": "restart",
    "message": "Service restarted successfully"
}
```

#### Get Service Logs

```http
GET /api/nodes/{node_id}/services/{service_name}/logs?lines=50
Authorization: Bearer {token}

Response 200:
{
    "service_name": "autobot-backend",
    "node_id": "01-Backend",
    "lines": 50,
    "logs": "Mar 15 10:00:00 backend autobot[1234]: INFO - Server started..."
}
```

### 5.4 Post-Sync Node Actions

Execute role-specific actions on nodes (build, restart, schema migration, dependency install).

#### Get Available Actions for a Node

```http
GET /api/roles/node-actions/{node_id}
Authorization: Bearer {token}

Response 200:
{
    "node_id": "02-Frontend",
    "actions": [
        {
            "role_name": "frontend",
            "display_name": "Frontend",
            "category": "build",
            "label": "Build (Frontend)",
            "command": "cd /opt/autobot/autobot-frontend && npm run build"
        },
        {
            "role_name": "frontend",
            "display_name": "Frontend",
            "category": "restart",
            "label": "Restart nginx",
            "systemd_service": "nginx"
        }
    ]
}
```

#### Execute an Action on a Node

```http
POST /api/roles/node-actions/{node_id}/execute
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
    "role_name": "frontend",
    "category": "restart"
}

Response 200:
{
    "success": true,
    "node_id": "02-Frontend",
    "role_name": "frontend",
    "category": "restart",
    "output": ""
}
```

### 5.5 Fleet Health

```http
GET /api/roles/fleet-health
Authorization: Bearer {token}

Response 200:
{
    "health": "healthy",
    "required_down": [],
    "optional_down": [],
    "detail": "All roles active"
}
```

Possible `health` values: `healthy`, `degraded` (optional roles offline), `critical` (required roles offline).

### 5.6 Health Check (No Auth Required)

```http
GET /api/health

Response 200:
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 86400.5,
    "database": "healthy",
    "nodes_online": 7,
    "nodes_total": 8
}
```

---

## 6. Ansible Ad-Hoc Commands via SLM

For running arbitrary commands via the SLM Python API, use the `PlaybookExecutor` or construct Ansible ad-hoc invocations programmatically.

### Python API Client for Ansible Ad-Hoc

```python
#!/usr/bin/env python3
"""Run Ansible ad-hoc commands on AutoBot fleet nodes via SLM API.

Wraps SLM API calls to simulate `ansible <group> -m shell -a "<command>"`.
"""

import asyncio
import json
import logging
import ssl
from typing import Optional

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SLM_URL = "https://172.16.168.19"


def _create_ssl_context() -> ssl.SSLContext:
    """Create permissive SSL context for self-signed certs."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def get_slm_token(
    session: aiohttp.ClientSession,
    username: str = "admin",
    password: str = "your_password",
) -> str:
    """Authenticate with SLM and return JWT token.

    Args:
        session: Active aiohttp session.
        username: SLM username.
        password: SLM password.

    Returns:
        JWT access token.
    """
    async with session.post(
        f"{SLM_URL}/api/auth/login",
        json={"username": username, "password": password},
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return data["access_token"]


async def ansible_adhoc(
    command: str,
    target_group: str,
    become: bool = False,
    module: str = "shell",
) -> dict:
    """Execute an Ansible ad-hoc command via SLM infrastructure API.

    This maps to running:
        ansible -i inventory/slm-nodes.yml <target_group> -m <module> -a "<command>"

    Args:
        command: Command or module arguments.
        target_group: Ansible inventory group (e.g., "infrastructure", "redis").
        become: Whether to use sudo.
        module: Ansible module name (default: "shell").

    Returns:
        Dict with execution results.
    """
    connector = aiohttp.TCPConnector(ssl=_create_ssl_context())
    async with aiohttp.ClientSession(connector=connector) as session:
        token = await get_slm_token(session)
        headers = {"Authorization": f"Bearer {token}"}

        # Use the manage_services playbook with shell override
        async with session.post(
            f"{SLM_URL}/api/infrastructure/execute",
            json={
                "playbook_id": "manage-services-adhoc",
                "variables": {
                    "target_host": target_group,
                    "shell_command": command,
                    "ansible_become": str(become).lower(),
                },
            },
            headers=headers,
        ) as resp:
            if resp.status != 200:
                # Fall back to slm-service-control playbook
                logger.info("Ad-hoc playbook not available, using service control")
                return await _fallback_service_control(
                    session, headers, command, target_group, become
                )
            data = await resp.json()
            execution_id = data["execution"]["execution_id"]

        # Poll for completion
        for attempt in range(30):
            await asyncio.sleep(2)
            async with session.get(
                f"{SLM_URL}/api/infrastructure/executions/{execution_id}",
                headers=headers,
            ) as status_resp:
                status_data = await status_resp.json()
                execution = status_data.get("execution", status_data)
                if execution["status"] in ("completed", "failed", "cancelled"):
                    return execution

        return {"status": "timeout", "output": "Execution timed out after 60s"}


async def _fallback_service_control(
    session: aiohttp.ClientSession,
    headers: dict,
    command: str,
    target_group: str,
    become: bool,
) -> dict:
    """Fall back to service control for simple service commands.

    Args:
        session: Active session.
        headers: Auth headers.
        command: Command to execute.
        target_group: Target group.
        become: Use sudo.

    Returns:
        Execution result dict.
    """
    # Parse service commands (systemctl restart nginx, etc.)
    parts = command.strip().split()
    if len(parts) >= 3 and parts[0] == "systemctl":
        action = parts[1]  # start, stop, restart, status
        service_name = parts[2]

        if action in ("start", "stop", "restart"):
            async with session.post(
                f"{SLM_URL}/api/orchestration/fleet/services/{service_name}/{action}",
                headers=headers,
            ) as resp:
                return await resp.json()

    return {"success": False, "output": "Command not supported via fallback", "returncode": -1}


async def main() -> None:
    """Demonstrate Ansible ad-hoc execution via SLM."""
    # Check memory on all infrastructure nodes
    print("=== Memory Usage (All Infrastructure) ===")
    result = await ansible_adhoc("free -m | head -2", "infrastructure")
    print(json.dumps(result, indent=2, default=str))

    # Check disk on redis node
    print("\n=== Disk Usage (Redis) ===")
    result = await ansible_adhoc("df -h / | tail -1", "redis")
    print(json.dumps(result, indent=2, default=str))

    # Restart nginx on frontend (with sudo)
    print("\n=== Restart nginx (Frontend) ===")
    result = await ansible_adhoc("systemctl restart nginx", "frontend", become=True)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
```

### curl Examples for Common Operations

```bash
# Authenticate and store token
TOKEN=$(curl -sk https://172.16.168.19/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Check fleet health
curl -sk https://172.16.168.19/api/roles/fleet-health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List all registered playbooks
curl -sk https://172.16.168.19/api/infrastructure/playbooks \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Execute update-all-nodes playbook
curl -sk https://172.16.168.19/api/infrastructure/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"playbook_id":"update-all-nodes","variables":{}}' \
  | python3 -m json.tool

# Restart nginx on frontend node
curl -sk -X POST https://172.16.168.19/api/orchestration/services/nginx/restart \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"02-Frontend"}' \
  | python3 -m json.tool

# Restart nginx across ALL nodes that have it
curl -sk -X POST https://172.16.168.19/api/orchestration/fleet/services/nginx/restart \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get services running on backend node
curl -sk https://172.16.168.19/api/nodes/01-Backend/services \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Get service logs from a node
curl -sk "https://172.16.168.19/api/nodes/01-Backend/services/autobot-backend/logs?lines=50" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Start all services in dependency order
curl -sk -X POST https://172.16.168.19/api/orchestration/start-all \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exclude":[]}' \
  | python3 -m json.tool
```

---

## 7. Using the SLM Dashboard UI

The SLM admin dashboard provides a graphical interface for fleet management. Access it at:

```
https://172.16.168.19/
```

### Dashboard Panels

| Panel | URL Path | Description |
|-------|----------|-------------|
| Fleet Overview | `/fleet` | All nodes with status, services, and health indicators |
| Node Detail | `/fleet/{node_id}` | Per-node services, logs, and actions |
| Infrastructure | `/infrastructure` | Playbook execution with progress tracking |
| Code Sync | `/code-sync` | Git version tracking and fleet sync operations |
| Services | `/services` | Fleet-wide service management (start/stop/restart) |
| Monitoring | `/monitoring` | Prometheus metrics and Grafana dashboards |
| Roles | `/roles` | Role definitions and node-role assignments |
| Settings | `/settings` | Global SLM configuration |

### Executing Commands from the UI

1. Navigate to **Infrastructure** panel
2. Select a playbook from the list (e.g., "Update All Nodes")
3. Optionally restrict to specific hosts using the **Limit Hosts** field
4. Provide any required variables
5. Click **Execute** -- progress streams in real time via WebSocket
6. View execution output in the activity log

### Service Control from the UI

1. Navigate to **Fleet Overview**
2. Click on a node card to expand its services
3. Use the **Start** / **Stop** / **Restart** buttons for individual services
4. Use the **Bulk Actions** menu for fleet-wide operations

---

## 8. Code Deployment via SLM

The SLM provides a two-step code deployment pipeline:

1. **Pull** -- fetch latest code from GitHub to the SLM server
2. **Fleet Sync** -- distribute code to all fleet nodes via Ansible

### Code Deployment Script

```python
#!/usr/bin/env python3
"""Deploy code updates to AutoBot fleet via SLM.

Two-step process:
1. Pull latest code from GitHub to SLM server (/opt/autobot/code_source)
2. Sync code to fleet nodes with rolling strategy

IMPORTANT: Use batch_size=1 to avoid git index.lock race conditions
during parallel fleet sync operations.
"""

import asyncio
import json
import logging
import ssl

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SLM_URL = "https://172.16.168.19"


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for self-signed certificates."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def deploy_code_to_fleet(
    strategy: str = "rolling",
    batch_size: int = 1,
    restart: bool = True,
) -> dict:
    """Deploy latest code to all fleet nodes.

    Args:
        strategy: Deployment strategy ("rolling" or "parallel").
            Rolling is recommended to prevent service disruption.
        batch_size: Number of nodes to update simultaneously.
            Use 1 to avoid git index.lock race conditions.
        restart: Whether to restart services after code sync.

    Returns:
        Dict with sync results from each node.
    """
    connector = aiohttp.TCPConnector(ssl=_create_ssl_context())
    async with aiohttp.ClientSession(connector=connector) as session:
        # Authenticate
        async with session.post(
            f"{SLM_URL}/api/auth/login",
            json={"username": "admin", "password": "your_password"},
        ) as auth_resp:
            auth_resp.raise_for_status()
            token = (await auth_resp.json())["access_token"]

        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Pull latest code from GitHub
        logger.info("Step 1: Pulling latest code from GitHub...")
        async with session.post(
            f"{SLM_URL}/api/code-sync/pull",
            headers=headers,
        ) as pull_resp:
            if pull_resp.status != 200:
                body = await pull_resp.text()
                logger.error("Pull failed: %s", body)
                return {"success": False, "error": body}
            pull_data = await pull_resp.json()
            logger.info("Pull result: %s", json.dumps(pull_data, indent=2))

        # Step 2: Sync to fleet nodes
        logger.info("Step 2: Syncing to fleet (strategy=%s, batch_size=%d)...", strategy, batch_size)
        async with session.post(
            f"{SLM_URL}/api/code-sync/fleet/sync",
            json={
                "strategy": strategy,
                "batch_size": batch_size,
                "restart": restart,
            },
            headers=headers,
        ) as sync_resp:
            if sync_resp.status != 200:
                body = await sync_resp.text()
                logger.error("Fleet sync failed: %s", body)
                return {"success": False, "error": body}
            sync_data = await sync_resp.json()
            logger.info("Fleet sync initiated: %s", json.dumps(sync_data, indent=2))

        # Step 3: Monitor sync progress
        job_id = sync_data.get("job_id")
        if job_id:
            return await _monitor_sync_job(session, headers, job_id)

        return sync_data


async def _monitor_sync_job(
    session: aiohttp.ClientSession,
    headers: dict,
    job_id: str,
) -> dict:
    """Monitor a fleet sync job until completion.

    Args:
        session: Active aiohttp session.
        headers: Auth headers.
        job_id: Fleet sync job UUID.

    Returns:
        Final job status dict.
    """
    for attempt in range(90):
        await asyncio.sleep(2)
        async with session.get(
            f"{SLM_URL}/api/code-sync/fleet/sync/{job_id}",
            headers=headers,
        ) as status_resp:
            if status_resp.status == 200:
                status = await status_resp.json()
                job_status = status.get("status", "unknown")
                logger.info("Sync progress: %s", job_status)

                if job_status in ("completed", "failed", "partial"):
                    return status

    return {"status": "timeout", "error": "Sync monitoring timed out after 3 minutes"}


async def main() -> None:
    """Execute fleet code deployment."""
    result = await deploy_code_to_fleet(
        strategy="rolling",
        batch_size=1,
        restart=True,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
```

### Code Deployment via curl

```bash
# Authenticate
TOKEN=$(curl -sk https://172.16.168.19/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 1: Pull latest code
curl -sk -X POST https://172.16.168.19/api/code-sync/pull \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Step 2: Sync to fleet (batch_size=1 to avoid index.lock races)
curl -sk -X POST https://172.16.168.19/api/code-sync/fleet/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy":"rolling","batch_size":1,"restart":true}' \
  | python3 -m json.tool
```

### Code Deployment via Ansible (Alternative)

```bash
# From the SLM server or dev machine with Ansible access:
cd /opt/autobot/autobot-slm-backend/ansible

# Update all nodes (code sync + service restart)
ansible-playbook -i inventory/slm-nodes.yml playbooks/update-all-nodes.yml

# Update specific node
ansible-playbook -i inventory/slm-nodes.yml playbooks/update-all-nodes.yml --limit 02-Frontend
```

---

## 9. Security Considerations

### Authentication and Authorization

- **JWT tokens** with configurable expiration (default: 1 hour)
- All API calls are **audit-logged** with username, IP address, action, and result
- Failed login attempts are recorded in the audit log (Issue #998)
- MFA support for sensitive SLM admin accounts

### Network Security

- **SSH key-based authentication** -- all fleet nodes use the `autobot` user with `~/.ssh/autobot_key`
- **TLS encryption** -- nginx reverse proxy with certificates on all nodes
- **Internal CA** -- self-signed certificates managed via the `rotate-certs.yml` playbook
- **Firewall rules** -- SLM API port 8000 restricted to `172.16.168.0/24` subnet (Issue #894)

### Command Execution Safety

- All commands are executed via **Ansible** (not raw SSH), providing:
  - Idempotency guarantees for service management
  - Privilege escalation control (`become` must be explicitly requested)
  - Execution audit trail through Ansible logs
- **Playbook validation** -- only registered playbooks can be executed via the infrastructure API
- **SSH StrictHostKeyChecking** is disabled for internal fleet communication (`BatchMode=yes`)
- **Command timeout** enforced at both the Ansible level and the SSH connection level (120s default)

### Operational Constraints

- **`batch_size=1`** is required for fleet sync to avoid git `index.lock` race conditions
- **Rolling deployment** strategy prevents fleet-wide outage during updates
- **Both inventories** (`production.yml` and `slm-nodes.yml`) are required for full fleet Ansible operations
- **Never use `--no-verify`** on git hooks or `--force` on deployments without explicit authorization

---

## 10. Complete Example: Multi-Node System Check

```python
#!/usr/bin/env python3
"""Complete multi-node system check via SLM API.

Demonstrates:
1. Authentication with JWT
2. Fleet health check
3. Node enumeration
4. Service status across fleet
5. Infrastructure playbook execution

This script provides a comprehensive fleet health report.
"""

import asyncio
import json
import logging
import ssl
from datetime import datetime

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SLM_URL = "https://172.16.168.19"


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for self-signed certificates."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def full_system_check() -> None:
    """Run comprehensive system check across all fleet nodes.

    Performs the following checks:
    1. SLM health status
    2. Fleet health (role availability)
    3. Node enumeration and status
    4. Per-node service status
    5. Fleet-wide service aggregation
    """
    connector = aiohttp.TCPConnector(ssl=_create_ssl_context())
    async with aiohttp.ClientSession(connector=connector) as session:
        # Authenticate
        async with session.post(
            f"{SLM_URL}/api/auth/login",
            json={"username": "admin", "password": "your_password"},
        ) as auth_resp:
            if auth_resp.status != 200:
                print(f"ERROR: Authentication failed (HTTP {auth_resp.status})")
                return
            token = (await auth_resp.json())["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'=' * 70}")
        print(f"  AutoBot Fleet System Check - {timestamp}")
        print(f"{'=' * 70}")

        # Check 1: SLM Health
        print(f"\n{'--- 1. SLM Server Health ---':^70}")
        async with session.get(f"{SLM_URL}/api/health") as resp:
            health = await resp.json()
            print(f"  Status:       {health['status']}")
            print(f"  Version:      {health['version']}")
            print(f"  Uptime:       {health['uptime_seconds'] / 3600:.1f} hours")
            print(f"  Database:     {health['database']}")
            print(f"  Nodes Online: {health['nodes_online']}/{health['nodes_total']}")

        # Check 2: Fleet Health
        print(f"\n{'--- 2. Fleet Health ---':^70}")
        async with session.get(
            f"{SLM_URL}/api/roles/fleet-health",
            headers=headers,
        ) as resp:
            fleet_health = await resp.json()
            print(f"  Overall:      {fleet_health['health'].upper()}")
            print(f"  Detail:       {fleet_health['detail']}")
            if fleet_health["required_down"]:
                print(f"  CRITICAL:     {', '.join(fleet_health['required_down'])}")
            if fleet_health["optional_down"]:
                print(f"  Degraded:     {', '.join(fleet_health['optional_down'])}")

        # Check 3: Node Status
        print(f"\n{'--- 3. Fleet Nodes ---':^70}")
        print(f"  {'Node ID':<22} {'IP Address':<18} {'Status':<10} {'Last Seen'}")
        print(f"  {'-' * 22} {'-' * 18} {'-' * 10} {'-' * 20}")

        async with session.get(
            f"{SLM_URL}/api/nodes",
            headers=headers,
        ) as resp:
            nodes_data = await resp.json()
            nodes = nodes_data.get("nodes", [])

            for node in nodes:
                node_id = node.get("node_id", "unknown")
                ip = node.get("ip_address", "unknown")
                status = node.get("status", "unknown")
                last_seen = node.get("last_heartbeat", "never")
                if isinstance(last_seen, str) and len(last_seen) > 19:
                    last_seen = last_seen[:19]
                print(f"  {node_id:<22} {ip:<18} {status:<10} {last_seen}")

        # Check 4: Fleet Services
        print(f"\n{'--- 4. Fleet Services ---':^70}")
        async with session.get(
            f"{SLM_URL}/api/orchestration/fleet/services",
            headers=headers,
        ) as resp:
            if resp.status == 200:
                fleet_svc = await resp.json()
                services = fleet_svc.get("services", [])
                print(f"  {'Service':<30} {'Running':<10} {'Stopped':<10} {'Failed'}")
                print(f"  {'-' * 30} {'-' * 10} {'-' * 10} {'-' * 10}")
                for svc in services:
                    name = svc.get("service_name", "unknown")
                    running = svc.get("running_count", 0)
                    stopped = svc.get("stopped_count", 0)
                    failed = svc.get("failed_count", 0)
                    indicator = " [!]" if failed > 0 else ""
                    print(f"  {name:<30} {running:<10} {stopped:<10} {failed}{indicator}")

        # Check 5: Available Playbooks
        print(f"\n{'--- 5. Available Playbooks ---':^70}")
        async with session.get(
            f"{SLM_URL}/api/infrastructure/playbooks",
            headers=headers,
        ) as resp:
            if resp.status == 200:
                pb_data = await resp.json()
                playbooks = pb_data.get("playbooks", [])
                print(f"  {'ID':<25} {'Category':<15} {'Duration'}")
                print(f"  {'-' * 25} {'-' * 15} {'-' * 20}")
                for pb in playbooks[:10]:
                    print(
                        f"  {pb['id']:<25} {pb['category']:<15} {pb['estimated_duration']}"
                    )
                if len(playbooks) > 10:
                    print(f"  ... and {len(playbooks) - 10} more")

        print(f"\n{'=' * 70}")
        print(f"  System check complete.")
        print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(full_system_check())
```

---

## 11. Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| `HTTP 401 Unauthorized` | Invalid or expired JWT token | Re-authenticate via `/api/auth/login` |
| `HTTP 404 Not Found` (playbook) | Playbook not registered in AVAILABLE_PLAYBOOKS | Check `/api/infrastructure/playbooks` for valid IDs |
| SSH connection refused | SSH key not deployed or wrong user | Verify `autobot_key` on target node: `ssh -i ~/.ssh/autobot_key autobot@<ip>` |
| Playbook timeout | Command takes longer than configured timeout | Increase timeout in request body or Ansible config |
| `Permission denied` on service control | Missing sudo privileges | Set `become: true` in request or use `--become` flag |
| Fleet sync `index.lock` error | Parallel git operations on same repo | Use `batch_size=1` in fleet sync requests |
| `502 Bad Gateway` on SLM | SLM backend still initializing | Wait 30-60 seconds after restart, then retry |
| Node shows `offline` | Heartbeat not received | Check SLM agent service: `ssh autobot@<ip> systemctl status slm-agent` |

### Debugging Steps

#### 1. Verify SLM Server is Running

```bash
# From any machine on the network
curl -sk https://172.16.168.19/api/health | python3 -m json.tool

# Expected: {"status": "healthy", ...}
```

#### 2. Verify SSH Connectivity to Fleet Nodes

```bash
# From SLM server (172.16.168.19)
ssh -i ~/.ssh/autobot_key autobot@172.16.168.20 hostname
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 hostname
ssh -i ~/.ssh/autobot_key autobot@172.16.168.22 hostname
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 hostname
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24 hostname
ssh -i ~/.ssh/autobot_key autobot@172.16.168.25 hostname
```

#### 3. Verify Ansible Connectivity

```bash
# From SLM server
cd /opt/autobot/autobot-slm-backend/ansible
ansible -i inventory/slm-nodes.yml infrastructure -m ping
```

#### 4. Check SLM Backend Logs

```bash
# On SLM server
journalctl -u autobot-slm-backend -n 100 --no-pager
```

#### 5. Check Node Service Status

```bash
# Via SLM API
TOKEN=$(curl -sk https://172.16.168.19/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -sk https://172.16.168.19/api/nodes/01-Backend/services \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

#### 6. Verify Ansible Inventories

Both inventory files must be used together for full fleet operations:

```bash
# From SLM server
ls -la /opt/autobot/autobot-slm-backend/ansible/inventory/
# Must contain: production.yml, slm-nodes.yml

# Verify inventory parses correctly
ansible-inventory -i inventory/slm-nodes.yml --list | python3 -m json.tool
```

### Error Recovery

#### Token Expired During Long Operation

```python
async def execute_with_retry(
    command: str,
    target_group: str,
    max_retries: int = 2,
) -> dict:
    """Execute with automatic re-authentication on token expiry.

    Args:
        command: Bash command to execute.
        target_group: Target node group.
        max_retries: Maximum retry attempts on auth failure.

    Returns:
        Execution result dict.
    """
    for attempt in range(max_retries + 1):
        try:
            result = await execute_on_node_group(command, target_group)
            return result
        except aiohttp.ClientResponseError as e:
            if e.status == 401 and attempt < max_retries:
                logger.warning("Token expired, re-authenticating (attempt %d/%d)", attempt + 1, max_retries)
                continue
            raise
    return {"success": False, "output": "Max retries exceeded", "returncode": -1}
```

#### Partial Fleet Sync Failure

When a fleet sync reports `partial` status, some nodes succeeded while others failed:

```bash
# Check which nodes failed
curl -sk "https://172.16.168.19/api/code-sync/fleet/sync/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for node in data.get('node_states', []):
    if node.get('status') != 'completed':
        print(f\"FAILED: {node['node_id']} - {node.get('error', 'unknown')}\")
"

# Retry sync for specific failed node
curl -sk -X POST https://172.16.168.19/api/code-sync/fleet/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy":"rolling","batch_size":1,"restart":true,"node_filter":["02-Frontend"]}' \
  | python3 -m json.tool
```

---

## Related Documentation

- [AutoBot Reference](../developer/AUTOBOT_REFERENCE.md) -- infrastructure IPs, deployment commands, service layout
- [Ansible Playbook Reference](ANSIBLE_PLAYBOOK_REFERENCE.md) -- complete playbook catalog
- [Configuration Guide](CONFIGURATION_GUIDE.md) -- SSOT config, environment variables
- [Service Management](../developer/SERVICE_MANAGEMENT.md) -- systemd service patterns
