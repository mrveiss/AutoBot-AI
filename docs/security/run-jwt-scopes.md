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
| `mcp:filesystem` | Read/write execution workspace files | Code scaffolding, artifact storage |

### Task Management

| Scope | Action | Use Case |
|-------|--------|----------|
| `task:read` | Read task state, comments, decisions | Status checks, context gathering |
| `task:write` | Update task status, post comments | Progress tracking, blockers |

### Agent Invocation

| Scope | Action | Use Case |
|-------|--------|----------|
| `agent:invoke` | Call sub-agents | Delegated work, orchestration |

## Default Scopes

When `mint_run_jwt()` is called without explicit scopes, the agent receives:

```python
["task:read", "task:write"]
```

This allows agents to:
- Read task details (requirements, acceptance criteria)
- Update task status and post comments

But NOT:
- Call sub-agents (requires explicit `agent:invoke` grant)
- Access knowledge base (requires explicit grant for RAG)

## Granting Additional Scopes

When a specific run requires additional access:

```python
token = mint_run_jwt(
    run_id,
    task_id,
    agent_id,
    tenant_id,
    scope=["task:read", "task:write", "mcp:knowledge", "agent:invoke"],
)
```

Examples:
- **Code review agents**: add `task:write` to post decisions
- **Research agents**: add `mcp:knowledge` for KB access
- **File-manipulation agents**: add `mcp:filesystem` for workspace I/O

## Implementation Checklist

- [x] `mint_run_jwt()` encodes scopes into JWT payload
- [ ] MCP bridges validate scopes before fulfilling requests (deferred)
- [ ] Agent code checks scopes before taking actions (deferred)
- [x] Scope validation is DEFENSIVE: reject if scope missing, don't assume
- [ ] Agent execution path docs include required scopes per agent type
- [ ] Logging includes scope grants and scope-denied events
- [ ] Audit logs track every scope use

## Scope Validation Pattern

When implementing scope checks in agent code:

```python
async def some_task_mutation(token: str, operation: str):
    claims = await validate_run_jwt(token)  # raises JWTDecodeError/JWTExpiredError on failure

    if "task:write" not in claims.get("scope", []):
        raise PermissionError(f"Scope 'task:write' required for {operation}")

    # Proceed with operation
```

## Denylist & Revocation

When a run completes or is cancelled, its JWT is immediately revoked by adding its JTI (JWT ID) to the Redis denylist:

```python
# fire-and-forget (end-of-run cleanup):
revoke_run_jwt(token)

# await confirmed write (breach-response / async contexts):
await revoke_run_jwt_async(token)
```

Revoked tokens are rejected by `validate_run_jwt()` even if signature is valid. The denylist is Redis-backed for high-throughput rejection checks.

## Security Properties

| Property | Guarantee |
|----------|-----------|
| **Expiry** | Tokens expire within 5 minutes (configurable via `RUN_JWT_TTL_SECONDS`) |
| **Revocation** | Immediate via Redis denylist (within milliseconds) |
| **Signature** | HS256 signed with `RUN_JWT_SECRET` (fallback: `AUTOBOT_JWT_SECRET`) |
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
