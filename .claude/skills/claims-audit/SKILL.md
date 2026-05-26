# /claims-audit

Regenerates `docs/verification.md` and `docs/verification-inventory.json` by walking the repo's documented capabilities and verifying each has a wired endpoint, test, or service definition.

Run this after any significant feature addition, deletion, or docs change to keep the verification artifact current.

## When to use

- After merging a feature PR to verify the capability is actually reachable
- After docs updates to check for drift between claims and implementation
- On a weekly schedule (see Scheduled execution below)
- When a capability is reported broken

## Phases

### Phase 1 — Extract claims

Walk these sources in order:

1. `README.md` — extract every bullet under "Features at a Glance", "Core Services", and "What AutoBot Does"
2. `docs/architecture/` — extract capability claims (services described as running, APIs described as exposed)
3. `docs/developer/` — extract capability claims (SDK, plugin system, NPU, fleet management)
4. `docs/system-state.md` — extract ✅ complete capabilities from the status table

For each claim, record:
```json
{
  "capability": "<short name>",
  "claim": "<verbatim excerpt>",
  "source": { "file": "<relative path>", "line": <line_number> }
}
```

Load existing inventory from `docs/verification-inventory.json` as a baseline. Merge new claims; preserve IDs of existing entries.

### Phase 2 — Verify each claim

For each claim, run these checks in order (first match wins):

| Check | Method | Evidence kind |
|-------|--------|---------------|
| API endpoint | `grep -rn "^@router\|^@app" autobot-backend/api/ --include="*.py"` matching the capability | `endpoint` |
| Router registration | Grep `autobot-backend/initialization/router_registry/` for the module path | `router` |
| Docker service | Grep `docker-compose.yml` for a service matching the capability name | `service` |
| Test file | `find autobot-backend/ -name "*test*.py" -o -name "test_*.py"` matching the capability | `test` |
| Implementation | `find autobot-backend/ -name "*.py"` matching the capability | `implementation` |

Assign status:
- **✅ wired** — endpoint + router registration found (or Docker service with healthcheck)
- **⚠️ partial** — implementation exists but endpoint or Docker wiring is missing; OR capability lives in a different service than claimed
- **❌ broken** — claim appears in docs but no endpoint, service, or test can be found; OR implementation exists but is provably unreachable (e.g., celery beat defined but not scheduled)

### Phase 3 — Write artifacts

**`docs/verification-inventory.json`** — update with current `status`, `evidence`, `notes`, and `generated_at`.

**`docs/verification.md`** — regenerate the full table using the inventory. Format:

```markdown
| # | Capability | Source Claim | Claim Location | Verified-by Artifact | Status | Notes |
```

Include:
- File:line links formatted as `[file.py:NN](../relative/path/file.py#LNN)` for IDE navigation
- Endpoint URLs where available
- Test file references

Update the Summary table counts at the top.

### Phase 4 — File discovery issues

For every claim with `status: "broken"`:

```bash
gh issue create \
  --repo mrveiss/AutoBot-AI \
  --title "discovery: <capability> — <one-line description of breakage>" \
  --label "discovery,priority: high,bug" \
  --body "$(cat <<'EOF'
## Finding

**Capability:** <capability>
**Claim source:** <file>:<line>
**Status:** ❌ broken

## Evidence

<what was found and what was missing>

## Impact

<who is affected and how>

## Suggested fix

<concrete action to make status ✅ wired>

*Filed by /claims-audit on $(date -u +%Y-%m-%d)*
EOF
)"
```

Record the filed issue URL in the inventory under `"discovery_issue"`.

## Output format

After running, print a summary:

```
claims-audit complete — 2026-05-26
  17 claims checked
  ✅ wired:   13
  ⚠️ partial:  3
  ❌ broken:   1

Discovery issues filed:
  - discovery: celery-beat missing from docker-compose — scheduled tasks never fire for Docker users
    → https://github.com/mrveiss/AutoBot-AI/issues/XXXX

Updated:
  docs/verification.md
  docs/verification-inventory.json
```

## Scheduled execution

This skill is intended to run weekly. Wire it to the background-worker daemon (depends on that daemon issue being shipped) via:

```yaml
# In celery_app.conf.beat_schedule:
"claims-audit-weekly": {
    "task": "tasks.claims_audit.run",
    "schedule": crontab(day_of_week="sunday", hour=2, minute=0),
}
```

Until the daemon is available, run manually:

```bash
claude /claims-audit
```

## Notes

- Only walk `docs/` and `README.md` for claims — do not grep source code for claims (implementation is the evidence, not the source of claims)
- Preserve existing claim IDs in `verification-inventory.json` to maintain stable references
- If a claim has `status: "wired"` and nothing has changed, re-verify quickly and update `generated_at` only
- The discovery-issue body must include a "Suggested fix" section — do not file empty or vague issues
- Link `verification.md` line numbers to file:line anchors using `#LNN` syntax for IDE navigation
