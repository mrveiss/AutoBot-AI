# Define a visual workflow that executes shell scripts in parallel across a distributed fleet

AutoBot's `distributed_shell` workflow step type fans a shell script out to multiple fleet nodes simultaneously using `asyncio.gather`.  Every node in the step's `nodes` list executes the script concurrently; the step succeeds when all nodes return exit code 0.

## Visual Builder — step-by-step

1. Open **Workflow Automation** → **Visual Builder**.
2. Drag a **Distributed Shell** block from the palette onto the canvas.
3. Click the block to open its configuration panel.
4. Fill in:
   - **Nodes** — select one or more enrolled fleet nodes (multi-select dropdown).
   - **Script** — paste or type the shell script body.
   - **Language** — `bash` (default) or `sh`.
   - **Timeout** — maximum seconds per node (1–3600, default 300).
5. Connect input and output edges to adjacent blocks.
6. Click **Save** and **Run**.

## Workflow definition (JSON)

```json
{
  "name": "Fleet health check — 3 scripts in parallel",
  "steps": [
    {
      "id": "collect-facts",
      "type": "distributed_shell",
      "data": {
        "nodes":    ["node-001", "node-002", "node-003"],
        "script":   "hostname && uname -r && df -h /",
        "language": "bash",
        "timeout":  30
      }
    },
    {
      "id": "check-services",
      "type": "distributed_shell",
      "data": {
        "nodes":    ["node-001", "node-002", "node-003"],
        "script":   "systemctl is-active autobot-agent nginx redis-server",
        "language": "bash",
        "timeout":  15
      }
    },
    {
      "id": "report",
      "type": "distributed_shell",
      "data": {
        "nodes":    ["node-001", "node-002", "node-003"],
        "script":   "echo \"Fleet health check complete on $HOSTNAME\"",
        "language": "bash",
        "timeout":  15
      }
    }
  ],
  "edges": [
    {"source": "collect-facts",  "target": "check-services"},
    {"source": "check-services", "target": "report"}
  ]
}
```

## Creating via API

```python
import httpx

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN = "your-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,  # dev only
)

NODES = ["node-001", "node-002", "node-003"]

# 1. Create the workflow
wf = client.post("/workflows", json={
    "name": "Fleet health check — 3 scripts in parallel",
    "steps": [
        {
            "id": "collect-facts",
            "type": "distributed_shell",
            "data": {"nodes": NODES, "script": "hostname && uname -r && df -h /", "timeout": 30},
        },
        {
            "id": "check-services",
            "type": "distributed_shell",
            "data": {"nodes": NODES, "script": "systemctl is-active autobot-agent", "timeout": 15},
        },
        {
            "id": "report",
            "type": "distributed_shell",
            "data": {"nodes": NODES, "script": 'echo "Done on $HOSTNAME"', "timeout": 15},
        },
    ],
    "edges": [
        {"source": "collect-facts",  "target": "check-services"},
        {"source": "check-services", "target": "report"},
    ],
}).json()

workflow_id = wf["id"]
print(f"Created workflow: {workflow_id}")

# 2. Execute it
run = client.post(f"/workflows/{workflow_id}/execute").json()
print(f"Run ID: {run['run_id']}")

# 3. Poll for results
import time
while True:
    result = client.get(f"/workflows/{workflow_id}/runs/{run['run_id']}").json()
    if result["status"] in ("completed", "failed"):
        break
    time.sleep(2)

# 4. Print per-node output for each step
for step_id, step_result in result.get("step_results", {}).items():
    print(f"\n=== {step_id} ===")
    for node_result in step_result.get("node_results", []):
        print(f"  {node_result['node_id']}: exit={node_result['exit_code']}")
        print(f"    stdout: {node_result['stdout'].strip()}")
```

## `distributed_shell` step config reference

| Field      | Type                  | Default  | Description                              |
|------------|-----------------------|----------|------------------------------------------|
| `nodes`    | list of node IDs      | required | Fleet nodes to target (must be ONLINE)   |
| `script`   | string                | required | Shell script body (no `$(...)` patterns) |
| `language` | `"bash"` or `"sh"`   | `"bash"` | Interpreter used on each node            |
| `timeout`  | integer (seconds)     | 300      | Per-node execution timeout (1–3600)      |

## Step output shape

```json
{
  "success": true,
  "total_duration_ms": 843,
  "failed_nodes": [],
  "node_results": [
    {
      "node_id":     "node-001",
      "exit_code":   0,
      "stdout":      "node-001\n5.15.0-91-generic\n",
      "stderr":      "",
      "duration_ms": 312,
      "success":     true
    },
    {
      "node_id":     "node-002",
      "exit_code":   0,
      "stdout":      "node-002\n5.15.0-91-generic\n",
      "stderr":      "",
      "duration_ms": 287,
      "success":     true
    }
  ]
}
```

## Remote execution — how it works

Each node in the step is contacted via the SLM execute endpoint:

```
POST /nodes/{node_id}/execute
{
  "command":  "hostname && uname -r",
  "language": "bash",
  "timeout":  30
}
```

- **Local nodes** (manager host): subprocess execution.
- **Remote nodes**: SSH via the SLM key (`SLM_SSH_KEY` env var, default `/home/autobot/.ssh/autobot_key`) using `node.ssh_user` and `node.ssh_port` from the node record.

Commands are validated against a shell-injection denylist before execution.  Forbidden patterns include backtick substitution, `$(...)`, pipe-to-bash, and others.  Use `$HOSTNAME` (env var) instead of `$(hostname)` (command substitution).

## Security constraints

The SLM execute endpoint rejects commands containing:

| Pattern | Reason |
|---------|--------|
| Backtick `` ` `` | Command substitution |
| `$(...)` | Command substitution |
| `<(...)` / `>(...)` | Process substitution |
| `; rm ` | Destructive chaining |
| `\| bash` / `\| sh` | Pipe-to-interpreter |
| `curl ... \| bash` | Remote code execution |

Set `ALLOWED_COMMANDS_PATTERN` on the SLM host to restrict commands to a regex allowlist.

## Prerequisites

- Fleet nodes enrolled in SLM (`POST /nodes` with node metadata).
- Nodes with `ONLINE` status (checked before execution).
- For remote nodes: SSH key at `SLM_SSH_KEY` path with access to `node.ssh_user@node.ip_address`.

## Architecture reference

- **Step handler** — `autobot-backend/orchestration/dag_executor.py` (`NodeType.DISTRIBUTED_SHELL`)
- **SLM execute endpoint** — `autobot-slm-backend/api/nodes_execution.py`
- **Full example** — `docs/examples/parallel_fleet_workflow.py`
