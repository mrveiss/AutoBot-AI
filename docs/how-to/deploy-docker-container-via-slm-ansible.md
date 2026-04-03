# Use the Service Lifecycle Manager to automate the deployment of a Docker container using an Ansible playbook

AutoBot's SLM (Service Lifecycle Manager) backend runs Ansible playbooks on enrolled fleet nodes.  The `POST /api/slm/deployments/docker` endpoint accepts a `DockerDeploymentRequest`, translates it into an Ansible `extra_vars` dict, and triggers the `deploy-hybrid-docker.yml` playbook on the target node — all without SSH access from the caller.

## How it works

```
AutoBot backend
  └─ POST /api/slm/deployments/docker
       └─ SLMDeploymentOrchestrator.deploy_docker()
            └─ SLMClient.create_deployment()
                 └─ SLM backend POST /deployments
                      └─ Ansible playbook runner
                           └─ deploy-hybrid-docker.yml → target node
```

The SLM handles SSH connectivity to the fleet node, Ansible inventory injection, and playbook execution.  AutoBot provides the high-level API and tracks the deployment status.

## Quick start — deploy a container via API

```python
import httpx

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN = "your-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,  # dev only
)

# Trigger a Docker deployment on node-001
response = client.post("/slm/deployments/docker", json={
    "node_id": "node-001",
    "playbook": "deploy-hybrid-docker.yml",
    "containers": [
        {
            "name": "my-app",
            "image": "myregistry/my-app",
            "tag": "v1.2.3",
            "ports": [
                {"host_port": 8080, "container_port": 80, "protocol": "tcp"}
            ],
            "environment": {
                "APP_ENV": "production",
                "LOG_LEVEL": "info"
            },
            "restart_policy": "unless-stopped"
        }
    ]
})

deployment = response.json()
print(f"Deployment ID: {deployment['deployment_id']}")
print(f"Status: {deployment['status']}")
```

## Request model — `DockerDeploymentRequest`

| Field        | Type                       | Default                    | Description                                     |
|--------------|----------------------------|----------------------------|-------------------------------------------------|
| `node_id`    | string                     | required                   | Enrolled SLM fleet node to deploy on            |
| `containers` | list of `DockerContainerSpec` | required                | One or more container definitions               |
| `playbook`   | string                     | `deploy-hybrid-docker.yml` | Ansible playbook filename to run on the SLM     |

### `DockerContainerSpec` fields

| Field            | Type                    | Default          | Description                                      |
|------------------|-------------------------|------------------|--------------------------------------------------|
| `name`           | string                  | required         | Container name (`docker run --name`)             |
| `image`          | string                  | required         | Docker image name (without tag)                  |
| `tag`            | string                  | `latest`         | Image tag                                        |
| `ports`          | list of `PortMapping`   | `[]`             | Host→container port mappings                     |
| `environment`    | dict                    | `{}`             | Environment variables passed to the container    |
| `restart_policy` | string                  | `unless-stopped` | Docker restart policy                            |

### `PortMapping` fields

| Field              | Type    | Default | Description       |
|--------------------|---------|---------|-------------------|
| `host_port`        | integer | required | Port on the host |
| `container_port`   | integer | required | Port in the container |
| `protocol`         | string  | `tcp`   | `tcp` or `udp`   |

## Ansible extra_vars injected by the SLM

The `SLMDeploymentOrchestrator` translates the request into a `docker_containers` extra_vars list that the playbook consumes:

```yaml
docker_containers:
  - name: my-app
    image: myregistry/my-app:v1.2.3
    ports:
      - "8080:80/tcp"
    environment:
      APP_ENV: production
      LOG_LEVEL: info
    restart_policy: unless-stopped
```

## Response — `DockerDeploymentStatus`

```json
{
  "deployment_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id":       "node-001",
  "status":        "running",
  "started_at":    "2025-10-15T14:30:00Z",
  "completed_at":  null,
  "error":         null
}
```

Poll `GET /api/slm/deployments/{deployment_id}` until `status` is `completed` or `failed`.

## Multi-step multi-node deployment (DeploymentOrchestrator)

For rolling out across multiple nodes with a sequential, parallel, or canary strategy, use the generic deployment API:

```python
import httpx, time

client = httpx.Client(
    base_url="https://autobot.example.com:8443/api",
    headers={"Authorization": "Bearer your-jwt-token"},
    verify=False,
)

# 1. Create a deployment (QUEUED state)
dep = client.post("/slm/deployments", json={
    "role_name":    "docker",
    "target_nodes": ["node-001", "node-002", "node-003"],
    "strategy":     "sequential",
    "playbook_path": "deploy-hybrid-docker.yml"
}).json()

deployment_id = dep["deployment_id"]
print(f"Created: {deployment_id} ({dep['status']})")

# 2. Execute it (QUEUED → RUNNING → COMPLETED/FAILED)
client.post(f"/slm/deployments/{deployment_id}/execute")

# 3. Poll for completion
while True:
    result = client.get(f"/slm/deployments/{deployment_id}").json()
    print(f"Status: {result['status']}")
    if result["status"] in ("completed", "failed", "cancelled"):
        break
    time.sleep(3)

# 4. Roll back if needed
if result["status"] == "failed":
    client.post(f"/slm/deployments/{deployment_id}/rollback")
    print("Rollback triggered")
```

## Available deployment strategies

| Strategy     | Behaviour                                                  |
|--------------|------------------------------------------------------------|
| `sequential` | Deploys one node at a time in order                        |
| `parallel`   | Deploys all nodes simultaneously via asyncio.gather        |
| `canary`     | Reserved for partial-fleet rollout (use with custom logic) |

## API reference

| Method | Path                                    | Description                                           |
|--------|-----------------------------------------|-------------------------------------------------------|
| POST   | `/api/slm/deployments/docker`           | Trigger a Docker deployment via SLM Ansible playbook  |
| POST   | `/api/slm/deployments`                  | Create a generic multi-role deployment (QUEUED)       |
| GET    | `/api/slm/deployments`                  | List active deployments (filter with `?status=`)      |
| GET    | `/api/slm/deployments/{id}`             | Get a single deployment                               |
| POST   | `/api/slm/deployments/{id}/execute`     | Execute a QUEUED deployment                           |
| POST   | `/api/slm/deployments/{id}/cancel`      | Cancel a QUEUED or RUNNING deployment                 |
| POST   | `/api/slm/deployments/{id}/rollback`    | Trigger rollback (adds ROLLBACK steps for each node)  |

## Prerequisites

- Fleet node enrolled in SLM (`POST /nodes` with node metadata and `ONLINE` status).
- SLM configured with Ansible and the `deploy-hybrid-docker.yml` playbook installed on the SLM host.
- Docker installed on the target fleet nodes.
- AutoBot backend started with the SLM client initialized (done automatically at startup).

## Architecture reference

- **Request/response models** — `autobot-backend/models/infrastructure.py`
- **SLMDeploymentOrchestrator** — `autobot-backend/services/slm/deployment_orchestrator.py`
- **DeploymentOrchestrator** (multi-node) — `autobot-backend/services/slm/deployment_orchestrator.py`
- **API routes** — `autobot-backend/api/slm/deployments.py`
- **SLM client** — `autobot-backend/services/slm_client.py`
- **Ansible playbook** — `autobot-slm-backend/ansible/roles/docker/tasks/main.yml` (via `deploy-hybrid-docker.yml`)
