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
| `mcp:web_fetch` | Outbound web-fetch bridge | Fetch external content |
| `mcp:filesystem` | Read-only local filesystem access | Read workspace files |

### Task Management

| Scope | Action | Use Case |
|-------|--------|----------|
| `task:read` | Read task state, comments, decisions | Status checks, context gathering |
| `task:write` | Update task status, post comments | Progress tracking, blockers |

### Execution

| Scope | Action | Use Case |
|-------|--------|----------|
| `agent:invoke` | Call sub-agents | Multi-agent workflows |

## Default Scopes

When `mint_run_jwt()` is called in heartbeat execution, the agent receives:

```python
["task:read", "task:write", "agent:invoke"]
```

This allows agents to:
- Read task details (requirements, acceptance criteria)
- Update task status and post comments
- Invoke sub-agents for complex workflows

But NOT:
- Access knowledge base (requires explicit grant for RAG)
- Directly access workspace files (requires explicit grant for mcp:filesystem)

## Granting Additional Scopes

When a specific run requires additional access:

```python
token = mint_run_jwt(
    run_id=str(run_id),
    task_id=task_id,
    agent_id=agent_id,
    tenant_id=tenant_id,
    scope=["task:read", "task:write", "mcp:knowledge", "agent:invoke"]
)
```

Examples:
- **Code review agents**: add `task:write` to post decisions
- **Research agents**: add `mcp:knowledge` for KB access
- **File-reading agents**: add `mcp:filesystem` for workspace I/O

## Implementation Checklist

- [x] `mint_run_jwt()` encodes scopes into JWT payload
- [ ] MCP bridges validate scopes before fulfilling requests (deferred)
- [ ] Agent code checks scopes before taking actions (deferred)
- [ ] Scope validation is DEFENSIVE: reject if scope missing, don't assume (deferred)
- [ ] Agent execution path docs include required scopes per agent type
- [ ] Logging includes scope grants and scope-denied events
- [ ] Audit logs track every scope use

## Scope Validation Pattern

When implementing scope checks in agent code:

```python
async def some_task_mutation(token: str, operation: str):
    try:
        claims = await validate_run_jwt(token)
    except JWTDecodeError:
        raise PermissionError("Invalid or expired run JWT")
    
    if "task:write" not in claims.get("scope", []):
        raise PermissionError(f"Scope 'task:write' required for {operation}")
    
    # Proceed with operation
```

## Denylist & Revocation

When a run completes or is cancelled, its JWT is immediately revoked by adding its JTI (JWT ID) to the Redis denylist:

```python
await revoke_run_jwt_async(token)  # Adds JTI to denylist, TTL = remaining JWT lifetime
```

Revoked tokens are rejected by `validate_run_jwt()` even if signature is valid. The denylist is Redis-backed for high-throughput rejection checks. Use `revoke_run_jwt_async()` in async contexts for guaranteed Redis write; `revoke_run_jwt()` is a sync fire-and-forget variant for non-critical cleanup paths.

## Security Properties

| Property | Guarantee |
|----------|-----------|
| **Expiry** | Tokens expire within 5 minutes (configurable via `RUN_JWT_TTL_SECONDS`) |
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
