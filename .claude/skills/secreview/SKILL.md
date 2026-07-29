---
name: secreview
description: Fast findings-first security review of a diff — emits a findings table within 3 tool calls, then verifies. Use when asked to security-review a diff, branch, uncommitted changes, or "check this for vulnerabilities". For deep multi-agent PR review use review-fleet instead; for whole-codebase audits use the security-auditor agent.
---

# Secreview — Findings Before Exploration

A diff-scoped security review that **emits before it explores**. Partial value
delivered in seconds beats total value delivered in minutes — a review that is
abandoned mid-exploration delivers nothing at all.

## The Ordering Contract (non-negotiable)

1. **One orientation call.** Read the diff. Nothing else.
2. **Findings table within 3 tool calls.** No preamble, no full-file reads, no
   codebase greps before the table is on screen.
3. **Verify after.** Only once the table is printed, read supporting files to
   confirm, downgrade, or drop each finding.
4. **Verdict last.** `BLOCK` / `APPROVE-WITH-NITS` / `APPROVE`.

Never reorder these. A finding stated with `CONFIDENCE: unverified` and corrected
in step 3 is useful; a perfectly-verified finding that never gets printed is not.

## When NOT to use this skill

| Situation | Use instead |
|---|---|
| Unbounded review of the branch, thoroughness over speed | built-in `/security-review` |
| Deep, recall-biased review of an open PR | `review-fleet` (10 parallel finder + verifier agents) |
| Whole-codebase security audit | `security-auditor` agent |
| Syntax, imports, types, lint before merge | `pre-merge-validate` |
| CI triage / PR merge cycle | `review` |

This skill is the **fast path**. Reach for it when the answer is wanted now.

## Step 1 — Orientation (ONE call)

```bash
# Pick whichever matches the ask; run exactly one.
git diff                                  # uncommitted changes
git diff --staged                         # staged changes
git diff origin/Dev_new_gui...HEAD        # whole branch vs base
gh pr diff <number>                       # a specific PR
```

If the diff exceeds ~1500 lines, add `--stat` first and review the highest-risk
files by name (auth, config, secrets, migrations, routers, middleware) — but
still emit the table within the 3-call ceiling. Say explicitly which files were
deferred; never let truncation read as "everything was covered".

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

## Step 3 — Verify

For each finding, read the file and its direct callers. Then update the row:
promote, downgrade, or strike it. State what changed — a finding that survives
verification is worth more than one that was never challenged.

For rename fallout specifically, grep the **old** identifier repo-wide; an AST
or import check misses aliased imports and test monkeypatch targets.

## Step 4 — Verdict

```
VERDICT: BLOCK | APPROVE-WITH-NITS | APPROVE
```

- `BLOCK` — any CRITICAL, or a HIGH that survived verification
- `APPROVE-WITH-NITS` — MEDIUM and below only
- `APPROVE` — nothing found after verification

## Follow-up

File a GitHub issue for every CRITICAL or HIGH that is out of scope for the
current change — discovered problems are fixed in scope or filed, never dropped.
In-scope findings get fixed in the same PR.

Keep the chat response to the table plus the verdict. If the review runs long,
write the detail to `docs/reports/secreview-<branch>.md` and reply with the path.
