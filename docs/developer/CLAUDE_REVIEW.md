# Code Review & Merge Rules

## Code Review Agent Requirements (MANDATORY)

**Every finder and verifier agent prompt MUST contain all three — refuse to dispatch if any missing:**

1. **Exact file list** from the PR diff:
   ```bash
   gh pr diff $PR_NUMBER --name-only > /tmp/review-files.txt
   cat /tmp/review-files.txt
   ```

2. **Scope restriction:** *"Use Read on these paths only. Do NOT Glob for other files in the repo."*

3. **Role + output format:** State the agent's specific angle (security, correctness, data-layer) AND output format (JSON with file, line, severity, evidence).

**Why:** Without the file list, agents verify against stale repo files. Without scope restriction, agents Glob unrelated files and produce noise.

---

## Code Review Methodology (3-Angle Protocol)

1. **Dispatch 3 parallel finder agents:** (a) security/auth/tenancy, (b) correctness/logic, (c) data-layer/edge-cases
2. **Ground every finding in the live diff.** Read actual PR diff (`gh pr diff <number>`) — never reason about files not confirmed on disk
3. **Run a verification pass.** Dedicated verifier re-reads each cited location and rejects findings it cannot ground in real code
4. **Post to the correct issue.** Confirm ownership before posting

---

## PR Review & Merge Checklist

After agents complete:

0. **Gate 0 — Squash-duplicate check:** Verify no commits are already in `Dev_new_gui` (see `docs/developer/CLAUDE_WORKFLOW.md` "Gate 0"). If all commits are duplicates, close without merging.
1. **Enumerate ALL open PRs:** `gh pr list --state open` before starting review
2. **Track in checklist:** One line per PR — nothing skipped
3. **Review each PR:**
   - Type checking: `npm run type-check` / `python -m mypy`
   - Syntax: `npm run lint` / `python -m black --check`
   - Imports: `python -c 'import <module>'` for each modified file
   - Call sites: grep for removed/renamed functions
4. **Merge:** each PR to `Dev_new_gui`
5. **Verify count:** PR count should be 0 after all merges

---

## Merge-Blocking Findings Gate (#10024)

Closes the review-to-merge race: a finding caught in review must not be merged
anyway (the #9968 / PR #9955 timeline — issue filed 3h before the PR merged).

**How to block a merge:**
1. File (or reuse) an issue describing the problem; reference the PR in its body
   (`#<pr-number>`).
2. Add the **`blocks-merge`** label to that issue.
3. The required check **`PR Blocking Findings`** (`.github/workflows/pr-blocking-findings.yml`)
   goes red while any open `blocks-merge` issue references the PR.

**To unblock:** close/resolve the issue, or remove the `blocks-merge` label, then
re-run the check (or push/sync the PR to re-trigger it).

Setup (owner, one-time):
- Create the label: `gh label create blocks-merge --color B60205 --description "Open issue blocks merging the PR it references"`.
- Add `PR Blocking Findings` as a **required** status check on `Dev_new_gui` and `main` so the merge button actually blocks (the workflow only reports status; branch protection enforces it).

**`required_conversation_resolution` decision — RECOMMEND ENABLE.** It is a
zero-code branch-protection toggle that blocks merge until every review
conversation is resolved. It covers the *review-comment* half of the race; the
`blocks-merge` gate above covers the *filed-issue* half that actually occurred.
Enable both (owner toggle: Settings → Branches → Dev_new_gui → "Require
conversation resolution before merging").

---

## Post-Merge Gap Audit

After ALL PRs merged:

1. **Import check:** `python -c 'import <module>'` for every modified Python file
2. **Call-site validation:** For every removed/renamed function, grep all callers
3. **Orphaned parameters:** Check function signatures don't break callers
4. **File parsing:** `python -m py_compile` (backend), `npx tsc --noEmit` (frontend)
5. **Discovery issues:** For ALL gaps found, file GitHub issues. Do NOT fix inline.

**Why:** Bugs like removed `_init_redis()` breaking 9+ call sites get caught here.

---

## Mandatory Post-Merge Dead Code Audit

After merging all PRs in a batch:

1. Run `/dead-code-audit` to discover new gaps introduced by merged code
2. File discovery issues for any new dead/orphaned code
3. Do NOT fix gaps inline — file issues under `dead-code` and `not-wired` labels

---

## Validation Gates Before Merging

**Use `/pre-merge-validate <PR>` before merging any code:**

0. Squash-Duplicate Detection (Gate 0)
1. Syntax + Imports
2. Call-Site Impact
3. Function Signatures
4. Targeted Tests (only changed files)
5. Type Check (TypeScript)
6. Linting (errors only, not warnings)

`/batch-implement` runs this automatically before creating PRs.

---

## CI Diagnosis

**Before declaring CI "stuck" or attempting to cancel/retrigger:**
- Confirm whether checks are actually failing vs. queued on a self-hosted runner
- Default assumption: checks are running normally, not broken
- Only cancel/retrigger when a check has been in a non-running state for >30 minutes with no activity

**Why:** Sessions wasted time canceling/retriggering smoke tests that were running normally.

---

## PR Template Format

This repo uses **custom headings** — NOT standard GitHub template sections:

| Heading | Purpose |
|---|---|
| **Thinking Path** | Your reasoning and approach |
| **What Changed** | Files/systems modified |
| **Verification** | Test output, curl, CI evidence |
| **Model Used** | Which Claude model ran this |

Always use these exact headings when creating or editing PR descriptions.

---

## Issue Ownership & Posting

- Before posting review findings or comments to any Paperclip/MVA issue, **verify the target issue is assigned to this agent**
- If the correct target is unclear, pivot to an agent-owned tracking issue
- PR authors cannot self-approve — post a detailed review comment instead
- **When posting comments:** write literal markdown text — never a raw JSON string or file path

---

## Posting Comments Correctly

When posting PR/issue comments or updating PR bodies:
- Write the literal text/markdown content
- Never pass a raw JSON string as the body
- Never pass a file path instead of file contents
- Verify the rendered comment after posting
