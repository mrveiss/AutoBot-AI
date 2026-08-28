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
4. **Merge:** each PR to `Dev_new_gui` — only with every required check green (see "Red CI Never Merges")
5. **Verify count:** PR count should be 0 after all merges

---

## Red CI Never Merges (#13665)

A red required check is a merge blocker, not an input to a judgement call. **Filing
a tracking issue for a failing check and merging anyway is forbidden** — that is the
exact anti-pattern this gate exists to stop (an api-wiring audit failed, got an issue
filed against it, and the PR merged regardless; the audit was failing for a real
reason).

The check is telling you the change is wrong, or that the check is wrong. Both are
root causes and both are yours to fix:

1. **Confirm it is actually red**, not queued. Queued checks on the singleton
   self-hosted runner are not failures — see "CI Diagnosis" below and verify the
   verdict against the head SHA from `gh api repos/{owner}/{repo}/pulls/N --jq
   '.head.sha'`, sorting check-runs by `started_at` (array order is not chronological,
   so a stale FAILURE can sit next to the real SUCCESS).
2. **Absence is not success.** A PR reporting "19 success, 0 failures" is still
   blocked if a required context never reported at all. Count reported contexts
   against `gh api repos/{owner}/{repo}/branches/Dev_new_gui/protection --jq
   '.required_status_checks.contexts[]'`.
3. **Name the cause before you debug the diff (#15139).** Five conditions render as
   the same red tile, and `gh pr checks` buckets every one of them under `fail` —
   `fail` there is **not** `conclusion: failure` and must be confirmed against the
   run object. Run `pipeline-scripts/ci_red_cause.py --pr N` (add `--json` to parse
   it). It reads `GET /actions/jobs/{id}`, the only endpoint carrying a `steps`
   array — `GET /commits/{sha}/check-runs` has none, so anything classifying from
   the check-runs listing alone is guessing.

   | cause | what happened | remedy |
   |---|---|---|
   | `runner-starvation` | job executed 0 steps — it never got a runner | re-queue |
   | `provisioning-failure` | first failing step is toolchain setup (`apt` exit 124) | re-queue |
   | `superseded` | `conclusion: cancelled` — a newer push retired the run | wait for the fresh run |
   | `test-failure` | first failing step is a work step | **fix the diff; never re-queue** |
   | `undetermined` | the cause could not be established | **treat as a real failure** |

   Read the **first** failing step, never the last: a setup failure makes later test
   steps fail downstream, so the last failure lies about the cause.

   **A named cause never makes a red check green.** The tool publishes no status and
   re-queues nothing; it exits 1 on any red whatever the cause, and exits 2 when
   nothing could be classified — which is never "clean".
4. **Root-cause and fix it** in the same PR. If the check itself is wrong, fix the
   check — in the same PR or a fast-follow that lands first.
5. **If it genuinely cannot be fixed now:** label the PR `blocked`, post a
   one-paragraph root-cause writeup on it, and move to the next issue. Do not merge,
   do not `--admin` past it, and do not interrupt a `/loop` to ask about it.

Three failed attempts on the same red check is an escalation, not a fourth attempt:
post the findings on the issue and move on.

**Applies identically in autonomous `/loop` mode.** The loop merges what is green;
red means the tick moves to the next non-colliding issue, never to a workaround.

---

## Merge-Blocking Findings Gate (#10024)

Closes the review-to-merge race: a finding caught in review must not be merged
anyway (the #9968 / PR #9955 timeline — issue filed 3h before the PR merged).

**How to block a merge:**
1. File (or reuse) an issue describing the problem; reference the PR in its body
   (`#<pr-number>`).
2. Add the **`blocks-merge`** label to that issue.
3. The required check **`No open blocks-merge issues reference this PR`** (the job
   in `.github/workflows/pr-blocking-findings.yml`, whose workflow display name is
   *PR Blocking Findings*) goes red while any open `blocks-merge` issue references
   the PR.

**To unblock:** close/resolve the issue, or remove the `blocks-merge` label, then
re-run the check (or push/sync the PR to re-trigger it).

Setup (owner) — **configured on `Dev_new_gui` and `main`** (2026-06-23):
- The `blocks-merge` label exists (`gh label create blocks-merge --color B60205 --description "Open issue blocks merging the PR it references"`).
- The required status-check **context is the job name** `No open blocks-merge issues reference this PR` — *not* the workflow name. GitHub matches required checks by the reported check-run name (the Actions job's `name:`), so requiring `PR Blocking Findings` would never match and would block every PR. Both branches now require the job-name context so the merge button actually blocks (the workflow only reports status; branch protection enforces it).

**`required_conversation_resolution` — ENABLED** on `Dev_new_gui` and `main`
(2026-06-23). This zero-code branch-protection toggle blocks merge until every
review conversation is resolved. It covers the *review-comment* half of the race;
the `blocks-merge` gate above covers the *filed-issue* half that actually occurred.

---

## Post-Merge Gap Audit

After ALL PRs merged:

1. **Import check:** `python -c 'import <module>'` for every modified Python file
2. **Call-site validation:** For every removed/renamed function, grep all callers
3. **Orphaned parameters:** Check function signatures don't break callers
4. **File parsing:** `python -m py_compile` (backend), `npx tsc --noEmit` (frontend)
5. **Discovery issues:** For ALL gaps found, file GitHub issues. Do NOT fix them inline **in this audit** — the PRs are already merged, so an inline fix here would bypass review entirely. Each gap gets its own issue and its own reviewed PR. (This is the narrow exception to Rule 6's fix-by-default; while *implementing*, an in-scope pre-existing bug is still fixed in the same PR.)

**Why:** Bugs like removed `_init_redis()` breaking 9+ call sites get caught here.

---

## Mandatory Post-Merge Dead Code Audit

After merging all PRs in a batch:

1. Run `/dead-code-audit` to discover new gaps introduced by merged code
2. File discovery issues for any new dead/orphaned code
3. Do NOT fix gaps inline in this audit — file issues under `dead-code` and `not-wired` labels, each to be fixed in its own reviewed PR. Findings are always **wire-it-in** issues, never deletion issues

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

**A deep queue is the hosted-runner cap, not a dead self-hosted pool (#15139).**
Measured 2026-08-28: **155** runs queued, **14** jobs executing — **13 of them on
`ubuntu-latest`, 1 on self-hosted** — with both self-hosted runners `online`. A
12-run sample of the queued runs found `ubuntu-latest` on every job. So queue depth
tracks the GitHub-hosted concurrency cap; it is neither a dispatch gate nor a starved
self-hosted pool, and **idle self-hosted runners next to a long queue is expected**,
not evidence of a fault. Re-measure before assuming otherwise:

```bash
gh api 'repos/{owner}/{repo}/actions/runs?status=queued&per_page=1' --jq .total_count
gh api repos/{owner}/{repo}/actions/runners --jq '[.runners[] | {name, status, busy}]'
```

A run queued past `WATCHDOG_STALL_MINUTES` (default **45**) is the threshold
`ci_dispatch_watchdog.py --check runner-starvation` reports on. Below it, waiting is
normal and your diff is not the reason.

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

**Posting comments correctly** — when writing a PR/issue comment or updating a PR body:

- Write the literal text/markdown content
- Never pass a raw JSON string as the body
- Never pass a file path instead of the file's contents
- Verify the rendered comment after posting
