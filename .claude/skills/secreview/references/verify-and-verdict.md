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
