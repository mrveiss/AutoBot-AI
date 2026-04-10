# MCP Bridge Process/Container Isolation

**Issue:** [#3229](https://github.com/mrveiss/AutoBot-AI/issues/3229)
**Author:** mrveiss
**Status:** shipped

## Problem

AutoBot MCP bridges ran as in-process FastAPI routers sharing the backend
event loop.  A blocking call, unhandled exception, or memory spike in one
bridge could stall or crash the entire backend.

## Architecture

    dispatcher (MCPDispatcher._call_bridge)
         |
         v
    IsolatedBridgeRegistry.get_or_create(bridge)
         |
         +--> IsolationMode.INPROCESS  -> existing HTTP path
         |
         +--> IsolationMode.SUBPROCESS -> IsolatedBridgeClient
         |          |
         |          v
         |    worker_entrypoint.py <bridge>
         |    (rlimits: CPU, AS, NOFILE, NPROC)
         |    JSON-RPC over stdio
         |
         +--> IsolationMode.CONTAINER  -> docker/mcp-bridges.yml
                    (cgroup limits + seccomp + read-only root)

### Components

| File | Role |
|---|---|
| `autobot-backend/services/mcp_isolation_config.py` | Policy resolver (mode + limits from env) |
| `autobot-backend/services/mcp_isolated_runtime.py` | Subprocess client, registry, circuit breaker |
| `autobot-backend/services/mcp_bridge_workers/worker_entrypoint.py` | Child process: applies rlimits, serves JSON-RPC |
| `autobot-slm-backend/ansible/roles/backend/templates/autobot-mcp-bridge@.service.j2` | Optional systemd unit with hardening |
| `docker/mcp-bridges.yml` | Optional docker-compose overlay with cgroup limits |

## Default Policy

| Bridge | Mode | Rationale |
|---|---|---|
| filesystem_mcp | subprocess | file I/O + path traversal risk |
| browser_mcp    | subprocess | external processes + network |
| vnc_mcp        | subprocess | network I/O |
| knowledge_mcp  | inprocess  | pure in-memory + ChromaDB client |
| sequential_thinking_mcp | inprocess | pure computation |
| structured_thinking_mcp | inprocess | pure computation |
| (others)       | global default | follows `MCP_ISOLATION_MODE` |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_ISOLATION_MODE` | `inprocess` | Global fallback when bridge has no explicit category |
| `MCP_ISOLATION_MODE_<BRIDGE>` | - | Per-bridge override (bridge name upper-cased) |
| `MCP_BRIDGE_CPU_LIMIT` | `30` | Default CPU seconds per worker (RLIMIT_CPU) |
| `MCP_BRIDGE_MEM_LIMIT_MB` | `512` | Default address-space cap per worker (RLIMIT_AS) |
| `MCP_BRIDGE_NOFILE_LIMIT` | `256` | Default open-file cap per worker (RLIMIT_NOFILE) |
| `MCP_BRIDGE_RESTART_MAX` | `5` | Worker restarts before circuit breaker trips |

Per-bridge overrides: `MCP_BRIDGE_CPU_LIMIT_BROWSER_MCP=60`, etc.

## Caller API

The MCP dispatcher API (`MCPDispatcher.dispatch`) is unchanged.  Isolation
is opt-in at the policy layer; callers and the registry HTTP surface are
untouched.  This satisfies the acceptance criterion "MCP registry and
dispatcher unchanged from the caller perspective."

## Failure Modes

- **Worker crash** -> auto-restart, counted against `restart_max`; after
  the budget is exhausted the bridge is marked permanently failed and
  subsequent dispatches return `success=False`.
- **Slow tool call** -> `asyncio.wait_for` timeout kills the worker
  (SIGKILL) and the next call respawns.
- **Parse error on response** -> surfaced as transport error, same recovery
  as crash.

## Validation

- Unit tests: `autobot-backend/services/mcp_isolation_config_test.py` (9 tests)
- Unit tests: `autobot-backend/services/mcp_isolated_runtime_test.py` (8 tests)
- Existing dispatcher tests: `autobot-backend/services/mcp_dispatch_test.py`
  continue to pass (isolation path bypassed because test bridges use the
  `knowledge_mcp` which stays in-process).

## Rollout

Isolation is **off by default** (`MCP_ISOLATION_MODE=inprocess`), so no
behaviour changes on deploy.  Enable on SLM Manager via `.env`:

    MCP_ISOLATION_MODE=subprocess          # enables high-risk bridges only
    MCP_ISOLATION_MODE_BROWSER_MCP=subprocess
    MCP_BRIDGE_MEM_LIMIT_MB_BROWSER_MCP=1024

Validate with:

    journalctl -u autobot-backend -f | grep mcp_isolation
    curl -s localhost:8001/api/mcp/health | jq
