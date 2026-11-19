## Step 2 — Emit the findings table (before any other read)

```markdown
| Sev | file:line | Issue | Fix |
|-----|-----------|-------|-----|
| HIGH | app/api/x.py:42 | Endpoint has no authz dependency | Add `Depends(require_role(...))` |
```

Severity: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.

Mark anything not yet confirmed against source as `(unverified)` in the Issue
cell. That flag is what makes early emission safe.

If the diff is genuinely clean, print the table header with `— no findings —`
and go straight to the verdict. Do not pad it with speculation.

## Review checklist

If the diff touches **path validation, session/chat ownership, plugin loading, or
secrets/credentials**, read the matching section of
[`docs/developer/THREAT_MODEL.md`](../../../../docs/developer/THREAT_MODEL.md) first — it
carries the trust boundary, the canonical enforcement point, and the invariants for each,
so the model is loaded instead of re-derived. It is one read, and it counts against the
3-call ceiling only when a listed subsystem is actually in the diff.

These categories have produced real hits in this repo — cover each one.

**Authz & identity**
- Route added or changed without an auth dependency (`@router.*` with no `Depends`)
- Hand-rolled role comparison instead of the canonical helper (`is_admin_role()`)
- Ownership check missing — can user A act on user B's resource?
- WebSocket auth: token read before `accept()`, close code correct

**Secrets & data exposure**
- Credentials, tokens, or keys written to disk, logs, or an error response
- Secret compared with `==` instead of a constant-time / canonical verifier
  (`verify_internal_api_key`)
- Internal IPs, hostnames, or filesystem paths leaking into outward artifacts
- `rsync --delete` or similar without an `.env` exclusion

**Injection & input**
- Unparameterised SQL, shell interpolation, template injection
- Path traversal on user-supplied filenames
- Deserialisation of untrusted input (`pickle`, `yaml.load`)

**Concurrency & state**
- TOCTOU between a check and its use
- Rate limiter or lease that can be bypassed by a second path to the same action
- In-process singleton assumed global across workers

**Refactor fallout** — the highest-yield category historically
- Renamed function/client with call sites left un-updated (grep the OLD name)
- Method-name shadowing after a move
- Changed return shape with callers still reading the old one
- Fail-open default introduced where the old path failed closed
