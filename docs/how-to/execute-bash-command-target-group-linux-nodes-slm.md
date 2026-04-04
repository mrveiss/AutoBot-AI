# Write a script to execute a bash command on a target group of Linux nodes using the Service Lifecycle Manager

AutoBot's SLM (Service Lifecycle Manager) exposes two complementary mechanisms for running shell commands across a fleet:

1. **Single-node** — `POST /nodes/{node_id}/execute` sends a command directly to one enrolled node.
2. **Node group (parallel fan-out)** — A workflow step of type `distributed_shell` fans the command out to a list of nodes simultaneously via `asyncio.gather`.

## Execute on a single node

```python
import httpx

SLM_URL = "https://slm.example.com"
TOKEN   = "your-slm-jwt-token"

client = httpx.Client(
    base_url=SLM_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,  # dev only
)

response = client.post("/api/nodes/node-001/execute", json={
    "command":  "df -h / && free -m && uptime",
    "language": "bash",
    "timeout":  30,
})

result = response.json()
print(f"exit={result['exit_code']}")
print(result["stdout"])
```

## Execute on a target group of nodes — standalone script

The fastest path for scripted fleet-wide execution is to loop over nodes and call `POST /nodes/{node_id}/execute` concurrently using `asyncio.gather`:

```python
"""
Execute a bash command on a target group of Linux nodes via the SLM.
All nodes run in parallel; results are collected per-node.
"""
import asyncio
import httpx

SLM_URL = "https://slm.example.com"
TOKEN   = "your-slm-jwt-token"

# Target node group
TARGET_NODES = ["node-001", "node-002", "node-003", "node-004"]

# The command to run on every node
COMMAND = "hostname && uname -r && df -h /"


async def execute_on_node(
    client: httpx.AsyncClient,
    node_id: str,
    command: str,
    timeout: int = 30,
) -> dict:
    """Run a bash command on a single SLM node and return the result."""
    try:
        resp = await client.post(
            f"/api/nodes/{node_id}/execute",
            json={"command": command, "language": "bash", "timeout": timeout},
            timeout=timeout + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "node_id":     node_id,
            "exit_code":   data.get("exit_code", -1),
            "stdout":      data.get("stdout", ""),
            "stderr":      data.get("stderr", ""),
            "duration_ms": data.get("duration_ms", 0),
            "success":     data.get("exit_code", -1) == 0,
        }
    except Exception as exc:
        return {
            "node_id":   node_id,
            "exit_code": -1,
            "stdout":    "",
            "stderr":    str(exc),
            "success":   False,
        }


async def execute_on_group(
    nodes: list[str],
    command: str,
    timeout: int = 30,
) -> list[dict]:
    """Execute a bash command on a group of nodes in parallel."""
    async with httpx.AsyncClient(
        base_url=SLM_URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        verify=False,
    ) as client:
        results = await asyncio.gather(
            *(execute_on_node(client, node_id, command, timeout) for node_id in nodes)
        )
    return list(results)


async def main():
    results = await execute_on_group(TARGET_NODES, COMMAND, timeout=30)

    print(f"\nResults for: {COMMAND!r}")
    print(f"{'Node':<12} {'Exit':>5}  Output")
    print("-" * 60)
    for r in results:
        status = "OK" if r["success"] else "FAIL"
        first_line = r["stdout"].splitlines()[0] if r["stdout"] else r["stderr"]
        print(f"{r['node_id']:<12} {r['exit_code']:>5}  [{status}] {first_line}")

    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\nFailed nodes: {[r['node_id'] for r in failed]}")
    else:
        print(f"\nAll {len(results)} nodes succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Execute on a node group via AutoBot workflow (distributed_shell step)

For persistent, repeatable group execution — including scheduling and result tracking — define a workflow with a `distributed_shell` step.  The DAG executor fans the script out to all nodes in parallel and stores per-node output.

```python
import httpx, time

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN    = "your-autobot-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)

# Create a workflow with one distributed_shell step
wf = client.post("/workflows", json={
    "name": "Fleet disk check",
    "steps": [{
        "id":   "disk-check",
        "type": "distributed_shell",
        "data": {
            "nodes":    ["node-001", "node-002", "node-003"],
            "script":   "df -h / && echo OK on $HOSTNAME",
            "language": "bash",
            "timeout":  30,
        },
    }],
    "edges": [],
}).json()

workflow_id = wf["id"]
print(f"Created workflow: {workflow_id}")

# Execute
run = client.post(f"/workflows/{workflow_id}/execute").json()
run_id = run["run_id"]

# Poll for results
while True:
    result = client.get(f"/workflows/{workflow_id}/runs/{run_id}").json()
    if result["status"] in ("completed", "failed"):
        break
    time.sleep(2)

# Print per-node output
for step_id, step_result in result.get("step_results", {}).items():
    print(f"\n=== {step_id} ===")
    for node_result in step_result.get("node_results", []):
        print(f"  {node_result['node_id']}: exit={node_result['exit_code']}")
        print(f"    {node_result['stdout'].strip()}")
```

## `POST /nodes/{node_id}/execute` reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | string | required | Shell script (max 32 KB) |
| `language` | string | `bash` | `bash` or `sh` |
| `timeout` | integer | `300` | Execution timeout in seconds (1–3600) |

### Response shape

```json
{
  "node_id":     "node-001",
  "job_id":      "a1b2c3d4-e5f6",
  "exit_code":   0,
  "stdout":      "node-001\n5.15.0-91-generic\n",
  "stderr":      "",
  "duration_ms": 312
}
```

## Security constraints

The SLM validates every command against a denylist before execution.  Forbidden patterns:

| Pattern | Reason |
|---------|--------|
| Backtick `` ` `` | Command substitution |
| `$(...)` | Command substitution |
| `<(...)` / `>(...)` | Process substitution |
| `; rm ` | Destructive chaining |
| `\| bash` / `\| sh` | Pipe-to-interpreter |

Use `$HOSTNAME` (environment variable) instead of `$(hostname)` (command substitution).

## Environment variables required

| Variable | Description |
|----------|-------------|
| `SLM_URL` | SLM backend base URL (used by AutoBot workflow executor) |
| `SLM_AUTH_TOKEN` | Bearer token for SLM API (used by AutoBot workflow executor) |
| `SLM_SSH_KEY` | SSH private key path for remote node access (default: `/home/autobot/.ssh/autobot_key`) |

## Architecture reference

- **Single-node execute endpoint** — `autobot-slm-backend/api/nodes_execution.py`
- **Distributed shell step handler** — `autobot-backend/orchestration/dag_executor.py` (`NodeType.DISTRIBUTED_SHELL`, `execute_distributed_shell()`)
- **Per-node HTTP call** — `autobot-backend/orchestration/dag_executor.py` (`_execute_on_node()`)
