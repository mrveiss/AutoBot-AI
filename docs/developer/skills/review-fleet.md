---
name: review-fleet
description: Dispatch a 10-angle parallel PR review fleet (finder agents + verifier agents) that posts only confirmed, deduplicated findings to a single PR comment. Use when asked for a high-effort or recall-biased PR review.
metadata:
  type: skill
---

# Review Fleet

Dispatches 10 parallel finder agents against a PR diff, runs verifiers on candidates, deduplicates by cross-angle agreement, and posts a single structured comment.

## Pre-flight

```bash
# Get PR diff file list and patch
PR_NUMBER=<number>
gh pr diff $PR_NUMBER --name-only > /tmp/fleet-files.txt
gh pr diff $PR_NUMBER > /tmp/fleet-diff.patch
cat /tmp/fleet-files.txt
```

If `--dry-run` is passed: print the agent prompts and file list, then stop. Do not dispatch agents.

## Phase 1 — Parallel Finder Agents

Dispatch all 10 angles at once with `Agent` tool calls in a single message. Each agent:

**Required in every agent prompt:**
- The exact file list from `cat /tmp/fleet-files.txt`
- Instruction: "Use Read on these paths only. Do NOT Glob for other files."
- The angle-specific focus (see below)
- Output format: JSON array of findings

**10 angles:**

| # | Name | Focus |
|---|------|-------|
| 1 | security | authz bypasses, IDOR, injection, secrets in code, missing ownership checks |
| 2 | correctness | off-by-one, null/undefined, error paths skipped, incorrect logic |
| 3 | api-contract | breaking changes to API signatures, missing/wrong response_model, schema drift |
| 4 | test-coverage | new code paths with no test, tests that only assert happy path, missing edge cases |
| 5 | deps | new imports from removed modules, version mismatches, circular deps |
| 6 | migrations | schema changes without migration, migration without rollback, missing index |
| 7 | observability | missing logging, silent error catches, metrics not recorded |
| 8 | a11y | missing aria attributes, non-semantic HTML, color-only indicators (frontend only) |
| 9 | i18n | hardcoded user-facing strings not wrapped in i18n, locale-sensitive formatting |
| 10 | dead-code | functions defined but never called, imports never used, unreachable branches |

**Finder agent output format** (each agent returns this JSON):
```json
[
  {
    "angle": "security",
    "file": "autobot-backend/api/analytics_quality.py",
    "line": 142,
    "severity": "BLOCKER|HIGH|MEDIUM",
    "title": "Short description",
    "evidence": "Exact quote from the diff or file showing the issue"
  }
]
```

If no findings: return `[]`. Do not fabricate. Do not include speculative issues.

## Phase 2 — Verifier Agents

For each finding from Phase 1, dispatch a verifier agent (batch to max 5 parallel):

**Verifier prompt must include:**
- The specific finding (file, line, evidence)
- The file list from `/tmp/fleet-files.txt`
- Instruction: "Read the actual file at the given line. Confirm this finding exists in HEAD code, not just the diff context. Return JSON with confirmed: true/false and confidence: 0.0-1.0."

**Verifier output format:**
```json
{
  "confirmed": true,
  "confidence": 0.92,
  "note": "Optional clarification"
}
```

Drop any finding where `confirmed: false` OR `confidence < 0.7`.

## Phase 3 — Deduplicate and Rank

1. **Deduplicate by file:line** — if multiple angles flagged the same location, merge into one finding, listing all angles: `"angles": ["security", "correctness"]`
2. **Rank by cross-angle agreement** — findings confirmed by 2+ angles rank highest
3. **Within tier:** rank BLOCKER > HIGH > MEDIUM

## Phase 4 — Ownership Check and Post

```bash
# Confirm the target issue is ours before posting
ISSUE_ID=<issue-or-tracking-id>
gh issue view $ISSUE_ID --json assignees -q '.assignees[].login'
```

If not assigned to this agent: post to the PR comment directly instead of the issue.

Post a single PR comment:
```bash
gh pr comment $PR_NUMBER --body "$(cat <<'EOF'
## Review Fleet — PR #<number>

**Angles run:** 10 | **Candidates:** <N> | **Confirmed:** <M>

### BLOCKERS
<!-- Only if any -->
- **[security + correctness]** `file.py:142` — Title
  > Evidence quote

### HIGH
- **[security]** `file.py:88` — Title
  > Evidence quote

### MEDIUM
- **[observability]** `file.py:201` — Title
  > Evidence quote

---
*Review Fleet: 10 finder angles + verifier pass. Unconfirmed findings dropped.*
EOF
)"
```

If zero confirmed findings: post "Review Fleet found no confirmed issues across 10 angles."

## Wiring into Paperclip Wake Payload

When a wake payload contains `{"type": "pr_review", "effort": "high"}` or `{"type": "pr_review", "fleet": true}`, trigger this skill automatically by including `/review-fleet <PR_NUMBER>` in the agent prompt.

## Regression Test

To verify the fleet catches known bugs, run against a PR known to have issues:
```bash
# Pick a PR with known IDOR or privilege escalation finding from history
KNOWN_BUGGY_PR=<pr-number-from-history>
/review-fleet $KNOWN_BUGGY_PR --dry-run   # Verify prompts look right
/review-fleet $KNOWN_BUGGY_PR             # Run and confirm finding appears in output
```
