# Run-Scoped JWT Scope Registry

## Overview

AutoBot agents receive run-scoped short-lived JWTs for heartbeat execution. Each JWT carries an explicit `scopes` claim limiting what the agent can access during that run, dramatically reducing credential blast radius.

**Why run-scoped JWTs?**
- Leaked long-lived API keys grant indefinite access until manual rotation
- Run-scoped JWTs expire within 5 minutes (default) and can be revoked immediately
- Each run has a unique token, limiting lateral movement across runs

## Scope Definitions

Scopes use the format `<domain>:<action>` for clarity and extensibility.

### Knowledge Base (MCP)

| Scope | Action | Use Case |
|-------|--------|----------|
| `mcp:knowledge` | Read KB embeddings, search documents | RAG queries during planning |
| `mcp:file` | Read/write execution workspace files | Code scaffolding, artifact storage |

### Task Management

| Scope | Action | Use Case |
|-------|--------|----------|
| `task:read` | Read task state, comments, decisions | Status checks, context gathering |
| `task:update` | Update task status, post comments | Progress tracking, blockers |

### Execution

| Scope | Action | Use Case |
|-------|--------|----------|
| `workspace:manage` | Create/manage execution workspaces | Browser QA, preview servers |

## Default Scopes

When `mint_run_jwt()` is called without explicit scopes, the agent receives:

```python
["task:read", "workspace:manage"]
```

This allows agents to:
- Read task details (requirements, acceptance criteria)
- Manage their own execution workspace (preview servers, QA browsers)

But NOT:
- Directly update task status (requires explicit grant or code review path)
- Access knowledge base (requires explicit grant for RAG)

## Granting Additional Scopes

When a specific run requires additional access:

```python
token = await mint_run_jwt(
    run_id,
    agent_id,
    scopes=["task:read", "task:update", "mcp:knowledge", "workspace:manage"]
)
```

Examples:
- **Code review agents**: add `task:update` to post decisions
- **Research agents**: add `mcp:knowledge` for KB access
- **File-manipulation agents**: add `mcp:file` for workspace I/O

## Implementation Checklist

- [x] `mint_run_jwt()` encodes scopes into JWT payload
- [x] MCP bridges validate scopes before fulfilling requests
- [x] Agent code checks scopes before taking actions
- [x] Scope validation is DEFENSIVE: reject if scope missing, don't assume
- [ ] Agent execution path docs include required scopes per agent type
- [ ] Logging includes scope grants and scope-denied events
- [ ] Audit logs track every scope use

## Scope Validation Pattern

When implementing scope checks in agent code:

```python
async def some_task_mutation(token: str, operation: str):
    claims = await validate_run_jwt(token)
    if not claims:
        raise PermissionError("Invalid or expired run JWT")
    
    if "task:update" not in claims.get("scopes", "").split(","):
        raise PermissionError(f"Scope 'task:update' required for {operation}")
    
    # Proceed with operation
```

## Denylist & Revocation

When a run completes or is cancelled, its JWT is immediately revoked by adding its JTI (JWT ID) to the Redis denylist:

```python
await revoke_run_jwt(token)  # Adds JTI to denylist, TTL = remaining JWT lifetime
```

Revoked tokens are rejected by `validate_run_jwt()` even if signature is valid. The denylist is Redis-backed for high-throughput rejection checks.

## Security Properties

| Property | Guarantee |
|----------|-----------|
| **Expiry** | Tokens expire within 5 minutes (configurable via `AUTOBOT_RUN_JWT_TTL_SECONDS`) |
| **Revocation** | Immediate via Redis denylist (within milliseconds) |
| **Signature** | HS256 signed with `AUTOBOT_JWT_SECRET` |
| **Scope Binding** | Scopes are claims in the token, validated at each use |
| **Audit Trail** | Every mint/revoke logged with run_id, agent_id, scopes |

## Future Extensions

Possible scope additions as the platform grows:

- `mcp:models` — access to model provider APIs
- `llm:execute` — call LLM endpoints
- `cache:read` — access to shared cache (Redis)
- `storage:read|write` — persistent storage access
- `webhook:invoke` — trigger external webhooks

Each new scope MUST be explicitly documented, granting code added, and validation added at every use site.
