# Code Review & Merge Rules

> Every claim in this doc (CI status, "done", a check's outcome) follows the
> **Verification** rule in `CLAUDE.md`: paste the command and its output, never assert.

## PR granularity

- **Batch same-scope issues into one PR by default** — one CI suite per batch, not per issue. Each issue must still be *fully* delivered; partial delivery never closes. Independent or different-risk changes get separate PRs, as does anything too large for one honest review pass. Write **one `Closes #N` per line** — `Closes #A, #B` links only #A.
- **Finish what you started — append before you open** (owner rule 2026-09-19). Before opening a new PR, check for an open PR the change can be appended to (same scope, risk, owner) and append, but only to a PR not yet queued for a train ([OWNER_RULES.md](OWNER_RULES.md) rule 2). Existing open PRs never block opening a new one (rule 1, no cap); finish started issues before starting new ones.
- **Same file (owner rule 2026-11-01, replaces the 2026-09-18 one-PR-per-file rule).** Check `ledger who task trainmaster`. If it is claimed, PRs may overlap on the same file and the trainmaster alone reconciles them when building a train; authors don't coordinate or wait on each other, and a file is off limits only while held. If it is unclaimed, overlapping work goes in a single PR. A conflict between a PR not in a train and main stays the author's to resolve ([OWNER_RULES.md](OWNER_RULES.md) rule 2).
- **A pushed PR ends the tick — never wait on its CI.** Pushing is the sweep point: check every *other* in-flight PR once (approval gate, CI verdict, behind-ness), act on what is green or red, then start the next scoped issue immediately. The PR just pushed is re-checked at the next sweep, never polled.

**The PR-granularity rules agree on "fewer PRs" and disagree on the unit.** Resolve in this order:

    same issue     -> one branch, never split
    same file      -> one PR only while no trainmaster is claimed
    same scope     -> batch into one PR
    already open   -> append, if not yet queued

When two apply, the **earlier line wins**. While a trainmaster is claimed, sharing a file is not a granularity criterion.

## Self-review before pushing: known self-inflicted patterns

Clustered from reviewer-caught defects across the last 20 merged PRs (#16860–#16973). This is
**review-caught** evidence, not confirmed CI-failure history — `gh pr checks`/`check-runs`
exposed current state only, not history, for merged PRs, so treat this as "what reviewers keep
catching," not "what breaks CI." Run through before pushing:

1. **Silent failure swallowing** — a caught exception, a `|| echo ''` fallback, or a default
   value that hides a real failure instead of surfacing it. (#16875, #16873, #16866, #16877)
2. **Loose/imprecise test assertions** — checking a prefix, substring, or proxy value
   (`startsWith`, an unanchored `grep`, a parent ref) instead of the exact result, letting a
   test pass vacuously. (#16909, #16902, #16884, #16876, #16866)
3. **Hardcoded UI strings** — still recurring despite "No hardcoded UI strings" in `CLAUDE.md`.
   (#16907, #16902, #16875)
4. **Missing negative/failure-case test coverage** — only the happy path is tested; the failure
   path a change is supposed to guard is not. (#16893, #16890, #16886)
5. **Auth/permission check ordering or completeness** — a check exists but runs after a bypass
   path, or is missing a resource-type/ownership condition. (#16886, #16927)
6. **Accessibility gaps** — missing ARIA/keyboard semantics or label/`for`-`id` associations.
   (#16973, #16875)
7. **Stale/cached state read instead of the live source of truth** — checking a local or cached
   field instead of the durable record; see `store_authority` under Essential Patterns in
   `CLAUDE.md`. (#16927)
8. **Wrong issue/branch reference in a comment or doc** — citing the wrong number, costing a
   dedicated fix PR later. (#16881, #16860)
9. **A new gate makes existing tests exercise a different path — and they fail like a stale
   expectation.** When a change adds an authorization gate, guard or middleware upstream, every
   test whose fixture predates it now short-circuits before reaching its own subject. The failure
   reads as `assert <new> == <old>` with a plausible new value, so the obvious repair is to update
   the assertion — which goes green while **deleting the coverage**. Ask instead: *did the observed
   value come from the subject, or from something that now precedes it?* The docstring usually
   names the subject. Fix the **fixture**, not the expectation.
   Three files in one PR (#17054): two VNC handshake tests whose fake user carried no `role` began
   asserting the gate's `close(1008)` instead of the handshake's `1011`, and a third whose
   `role: "user"` stopped reaching `accept()` at all. Re-pinning those expectations would have
   removed the only coverage of the handshake-failure path and of the accept path, and left the
   gate's own headline case — a signed-in account *without* the permission — tested by nothing.
   The tell that it is this pattern rather than drift: **the "corrected" expectation duplicates
   what the new gate's own suite already asserts.** If updating a test makes it a second copy of a
   neighbour, it has stopped testing its own subject. Fixture fixes preserve coverage; expectation
   fixes spend it.
10. **Prose, a branch or a default that no input can reach — read it as a wrong gate, not a
   wrong message.** A conditional message whose else-branch describes a state the surrounding
   `when:`/`if` excludes is a *readable* trace of a gate hole: the author of the message knew
   the state was possible, and the gate says it is not. One of the two is wrong, and it is
   usually the gate. The repair that feels tidy — delete the unreachable text — destroys the
   only visible evidence and leaves the hole.
   `add_apt_repository_idempotent.yml` (#17897): the post-add failure message offered "No source
   for this repository was previously configured here", while both post-add tasks were gated on
   `_apt_repo_verdict != 'usable'`. That excludes `MISSING` — the one state with no prior source,
   and the one state where *nothing had been verified at all*, because the verdict short-circuits
   to `'usable'` whenever presence is not `PRESENT`. So a fresh install added the repo, verified
   nothing, and died three steps later on apt's bare "No package matching 'postgresql-16' is
   available". The dead sentence was visible before any of that was understood.
   **Check:** for each branch of a conditional message or default, name an input that reaches it.
   None → inspect the gate. Then pin it: derive the firing states by evaluating the **real**
   predicate, never from the set the test says *should* fire (that version of the guard passes
   with the defect reinstated).
   Related tell — a gate written as the **negation of a neighbouring fact** (`!= 'usable'`,
   `not preserve_ok`) rather than as the condition it means. Both spellings were true in the
   MISSING case, so renaming the variable preserved the hole across two revisions. Write the
   predicate the action means — here, mirroring the add's own condition.

## Pre-handover checklist: before the head goes to the train coordinator (#19285)

About half the PRs handed over on 2026-10-22/23 needed a fix-first round for one of these.
Check each before sending the PR# and head:

1. **Every guard or test the body claims exists and runs.** Name it by file and test, and
   confirm it ran in your pre-push or local run (#19257 claimed a smoke-credential guard that
   did not exist).
2. **Ceilings are met by splitting, never by trimming.** A file over its size ceiling gets a
   module or helper extracted; shortening comments, docstrings or log text to fit is a finding
   (#19208, #19201, and #19360's first head).
3. **Every cited owner decision is quoted on its issue,** with the date, before the PR cites it
   (#19216, #19259).
4. **The whole-tree guards pass on the branch:** symbol forks, isolated-git, file size, reach.
   Machine-checked: pre-push runs them on every push (`ALWAYS_RUN` in
   `tools/lint/prepush_selection.py`, #18808), so a green pre-push covers item 4. A new
   symbol that reuses an existing name (#19205, #19215) is what the symbol-fork ratchet catches.

5. **Local runs respect the shared machine (owner rule, 2026-10-23).** Only the test you changed
   (owner, 2026-11-02), run under the `machine:heavy-run` lock with a hold of at most 20
   minutes; never a full local `repo_tests` suite (CI is the full gate). Train pushes go first,
   and a hold whose reason says "train push waiting" is released at the next test boundary.

Items 1 and 3 need a reader; 2 is caught when a reviewer diffs the comments; 4 is automatic.

## CodeRabbit and merge trains (#19284)

- **Admission:** a member PR joins a train only once its own CodeRabbit threads are resolved.
  Its code is reviewed there, once.
- **Train PRs skip automatic review** (`.coderabbit.yaml` `ignore_title_keywords: ["train("]`).
  The coordinator reviews the train's own commits (fixes and merge resolutions) and requests
  `@coderabbitai review` by hand when a fix is substantial. Whole-diff train reviews re-opened
  approved member code after green CI: train 74 (#19191) took 9 and then 4 threads, each costing
  a full CI rerun.

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

0. **Gate 0 — Squash-duplicate check:** Verify no commits are already in `main` (see `docs/developer/CLAUDE_WORKFLOW.md` "Gate 0"). If all commits are duplicates, close without merging.
1. **Enumerate ALL open PRs:** `gh pr list --state open` before starting review
2. **Track in checklist:** One line per PR — nothing skipped
3. **Review each PR:**
   - Type checking: `npm run type-check` / `python -m mypy`
   - Syntax: `npm run lint` / `python -m black --check`
   - Imports: `python -c 'import <module>'` for each modified file
   - Call sites: grep for removed/renamed functions
4. **Merge:** each PR to `main` (approved PRs land via a train, see "Merge trains") — only with every required check green (see "Red CI Never Merges")
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

1. **Confirm it is actually red**, not queued. Queued checks on the self-hosted
   runner are not failures — see "CI Diagnosis" below and verify the
   verdict against the head SHA from `gh api repos/{owner}/{repo}/pulls/N --jq
   '.head.sha'`, sorting check-runs by `started_at` (array order is not chronological,
   so a stale FAILURE can sit next to the real SUCCESS).
2. **Absence is not success.** A PR reporting "19 success, 0 failures" is still
   blocked if a required context never reported at all. Count reported contexts
   against `gh api repos/{owner}/{repo}/branches/main/protection --jq
   '.required_status_checks.contexts[]'`.
3. **Name the cause before you debug the diff (#15139).** Five conditions render as
   the same red tile, and `gh pr checks` buckets every one of them under `fail` —
   `fail` there is **not** `conclusion: failure` and must be confirmed against the
   run object. Run `pipeline-scripts/ci_red_cause.py --pr N` (add `--json` to parse
   it). It reads `GET /actions/jobs/{id}`, the only endpoint carrying a `steps`
   array — `GET /commits/{sha}/check-runs` has none, so anything classifying from
   the check-runs listing alone is guessing.

   | cause | what happened | at fault | remedy |
   |---|---|---|---|
   | `runner-starvation` | job executed 0 steps — it never got a runner | environment | nothing ran; push a new head commit |
   | `provisioning-failure` | first failing step is toolchain setup (`apt` exit 124) | environment | no test result; push a new head commit |
   | `superseded` | `conclusion: cancelled` — a newer push retired the run | neither | wait for the run already queued on the current head |
   | `test-failure` | first failing step is a work step | **the diff** | fix the diff |
   | `undetermined` | the cause could not be established | **assume the diff** | establish the cause before acting |

   Read the **first** failing step, never the last: a setup failure makes later test
   steps fail downstream, so the last failure lies about the cause.

   **`infrastructure: true` means the diff is not indicted — it does NOT mean
   re-running will fix it (#15139).** Measured on run `33149960063`:
   `POST /actions/runs/{id}/rerun-failed-jobs` reported success and advanced the run
   to `attempt=2`, but the failed matrix leg `python-suite shard 12/12` was **carried
   forward, not re-executed** — same job id, same `started_at` — and only its
   dependents re-ran 18 minutes later, so the `python-suite` rollup failed again on
   `Fail if any shard failed`. All fourteen already-executed jobs kept their original
   attempt-1 timestamps. Re-queueing twice and getting the same red does not mean the
   classifier is wrong; it means the remedy is.

   What is structurally guaranteed instead: **a new head commit starts a new run at
   `attempt=1`**, and an attempt-1 run has no previous attempt to carry a job forward
   from, so every job must execute. That guarantees re-execution — not success.

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
red means the tick moves to the next issue, never to a workaround.

---

## Review comments are answered before a relaunch and before merge

CodeRabbit is advisory ([OWNER_RULES.md](OWNER_RULES.md) rule 12, replaces the 2026-09-25 "no CI while threads are unresolved"): it never blocks a PR opening or its first CI run, but every comment is answered before any CI relaunch and before merge. Resolving a thread costs **no CI**; a CI cycle costs ~35 minutes on a serialized shard queue. A
reviewer who has already named what will break is evidence that has been paid for, so read it before spending a relaunch.

Measured: one PR spent **four cycles** discovering guards one at a time while fourteen review
comments sat unread behind them.

**A resolution needs an argument, not a click.** The count of unresolved threads is the gate, and
the count is satisfiable without the substance — so the gate measures the wrong thing unless
resolutions carry replies. Two shapes both count as resolved and only one is:

    replied with what changed, or why it does not apply   -> resolved
    clicked resolve, nothing on the record                -> the finding is gone, not answered

When sweeping a PR for eligibility, **read the resolutions, not just the number.** A thread
resolved silently on a PR that then fails on the thing the reviewer named is the gate defeating
itself, and it will look like a passing check.

**Reply before the fix is pushed, and say so.** A resolved thread whose fix is still local reads to
the next person as *already fixed on this branch*. State that the change is committed and not yet
pushed, so nobody infers it from the diff.

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

Setup (owner) — **configured on `main` and `release`** (2026-06-23):
- The `blocks-merge` label exists (`gh label create blocks-merge --color B60205 --description "Open issue blocks merging the PR it references"`).
- The required status-check **context is the job name** `No open blocks-merge issues reference this PR` — *not* the workflow name. GitHub matches required checks by the reported check-run name (the Actions job's `name:`), so requiring `PR Blocking Findings` would never match and would block every PR. Both branches now require the job-name context so the merge button actually blocks (the workflow only reports status; branch protection enforces it).

**`required_conversation_resolution` — ENABLED** on `main` and `release`
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

## Merge trains

The trainmaster (PR-coordinator session) alone builds and lands trains: merge commits, never squash, two CI slots, two trains may run in CI, and only the one landing next is built and fixed. Authors send the PR number and head, then stop pushing to a queued head unless asked; a head moved only by merging main stays in line, and any other new commit needs a fresh look. CodeRabbit never blocks a first CI run; a relaunch answers open threads first. Full list: [`OWNER_RULES.md`](OWNER_RULES.md).

## CI Diagnosis

**Before declaring CI "stuck" or attempting to cancel/retrigger:**
- Confirm whether checks are actually failing vs. queued on a self-hosted runner
- Default assumption: checks are running normally, not broken
- Only cancel/retrigger when a check has been in a non-running state for >30 minutes with no activity
- Never cancel a `train-*` branch's runs or any run under a live `ci-slot` ledger hold (`ledger holds | grep ci-slot`), except that the conflict gate (`pr-merge-conflict-gate.yml`, #19769) cancels a train with a real merge conflict, because it can't land; the trainmaster owns CI priority ([OWNER_RULES.md](OWNER_RULES.md))

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

- Before posting review findings or comments to an issue, **verify it is the issue the work belongs to**
- If the correct target is unclear, file a tracking issue and link it
- PR authors cannot self-approve — post a detailed review comment instead

**Posting comments correctly** — when writing a PR/issue comment or updating a PR body:

- Write the literal text/markdown content
- Never pass a raw JSON string as the body
- Never pass a file path instead of the file's contents
- Verify the rendered comment after posting
