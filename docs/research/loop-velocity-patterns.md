# Why commit progress feels slow — recurring patterns in the loop/subagent workflow

Measured on AutoBot-AI, `origin/Dev_new_gui`, 2026-08-29. All numbers from git/gh, not estimates.

## Headline

Throughput is **not** slow: ~30 commits/day, median PR open→merge **2.09 h**, median CI run
**3.8 min**, 102/120 recent CI runs green. The loop produces plenty. What it does badly is
**convert produced work into landed commits**, and it **generates work faster than it lands it**.

## Pattern 1 — Abandonment in worktrees (largest single leak)

| Metric | Value |
|---|---|
| Worktrees | 92 |
| Branches not merged into base | 91 |
| Unlanded commits sitting on them | **401** |
| Branches that NEVER got a PR | **32** |
| Modal last-commit age | 10–14 days |

401 commits of finished work are parked. Each was paid for in full (design, code, guards, tests)
and returns nothing. The `/loop` starts a new worktree per tick and rarely returns to a previous one.

## Pattern 2 — Discovery outruns delivery 2:1

21-day window: **800 issues opened, 408 closed, net +392.**
Only 2 of 17 days were net-negative. The "never idle → then discovery" rule is reached on most
ticks, and every discovery tick files more than the delivery ticks close. The backlog is
predominantly the loop's own output, so "slow progress" is partly a moving denominator.

## Pattern 3 — Self-referential maintenance dominates the diff

Last 160 commits: `fix` **98**, `test` 17, `feat` **8**.
14-day window: **39 / 371** commits are guard / ratchet / allowlist / exemption work — guards being
fixed, scoped, and re-ratcheted. Issue-title tokens across 800 issues: `test` 117, `guard` 54,
`tech`+`debt` 55. A large fraction of capacity maintains the scaffolding that polices capacity.

## Pattern 4 — Fan-out that must reconverge on every change

30-day file-touch counts: 11 i18n locale files at **34 touches each** (374 touches for ~34 logical
changes), `types/generated/api.ts` **55**, `ssot_config.py` 26, CI workflows 26+21,
size-ratchet baselines 23+23. Every user-visible change carries a mandatory 11-way edit plus a
regenerate — mechanical drag on each PR and the main conflict surface across 90 parallel branches.

## Pattern 5 — CI thrash, not CI slowness

`issue-15238-path-roots`: **73 CI runs**. `issue-15276-provider-keys`: 25. 12 cancelled runs in the
last 120. The pipeline is fast; the cost is push→fail→push loops, i.e. verification happening on
CI instead of locally before the push.

## Pattern 6 — Parallel production, serial landing

90 branches in flight, **1 open PR**. Subagents fan out to produce work concurrently and then it
queues behind a single merge lane. Median PR is only 370 LOC / 4 files, so the lane is not being
saturated by big changes — it is simply used one at a time.

## Pattern 7 — Per-PR fixed overhead vs tiny payloads

157 of the last 160 commits close exactly one issue; only 25 cite two or more, despite
`CLAUDE.md` explicitly allowing `Closes #A, #B` for same-scope work. Each 370-LOC PR pays full
worktree + rebase + guard + review + evidence-closure overhead.

## What actually changes the number

1. **Drain before starting.** A loop tick that begins by landing one parked branch converts
   existing sunk cost instead of adding to it. 401 commits of inventory is ~13 PRs of value.
2. **Cap work-in-progress.** A hard ceiling on live worktrees forces closure before opening.
3. **Make discovery net-negative-capable.** Cap issues filed per tick, or require each discovery
   tick to close at least as many as it files.
4. **Batch same-scope issues.** The i18n/guard/test-guard families are the obvious candidates —
   they touch the same files and currently generate one PR each.
5. **Run the guard suite locally before push.** Kills the 73-run branches.
6. **Time-box guard work.** It is 10%+ of commits and produces no product change.

---

# Part 2 — Fixes, one per pattern

Two mechanisms turned out to be the crux, and both are *already built*:

- `~/.claude/scripts/backlog-governor.sh` **is** wired (`~/.claude/settings.json:607`) and **is**
  sitting at `RED`. But RED = `GOVERNOR_RATE_RED=2`/hour = **48 issues/day**, while closure runs at
  **19.4/day**. The tightest brake the system has is 2.5x the drain rate. It is working as
  configured; the configuration cannot ever produce a shrinking backlog.
- `scripts/hooks/session-stop-orphan-check.sh:23-28` **exits early when inside a worktree** — the
  exact location of all 401 unlanded commits. It is blind to the real orphan, and it auto-files
  issues, so it feeds Pattern 2 while missing Pattern 1.

## P1 — 401 unlanded commits, 32 branches never PR'd

**Cause:** nothing inspects a worktree at session end; the loop opens a new one per tick.
**Fix:**
1. Invert the worktree guard in `session-stop-orphan-check.sh` — inside a worktree, if
   `git rev-list --count origin/Dev_new_gui..HEAD > 0` and no PR exists for the branch, emit a
   blocking Stop message naming the branch and commit count. Do not auto-file an issue.
2. Add `scripts/drain-parked.sh`: ranks the 91 branches by commits-ahead x rebase-cleanliness.
3. `drain/SKILL.md` §1 currently says "Drain the PR queue first". Change to
   "**Drain the PR queue, then land one parked branch**" — with 1 open PR and 91 parked branches,
   step 1 is a no-op today.

**Recovers:** 401 commits ~ 13 PRs of already-paid-for work.

## P2 — net +392 issues in 21 days

**Cause:** the governor's rate constants are absolute, not derived from closure.
**Fix:** replace `RATE_GREEN/AMBER/RED` constants with a budget computed from the trailing-7-day
close rate: RED = 1.0x closes, AMBER = 1.5x, GREEN = 2.0x. At today's numbers RED becomes
~19/day instead of 48/day, and the backlog can actually shrink.
**Also:** stop `session-stop-orphan-check.sh` auto-creating issues (see P1) — it files without
closing by construction.

## P3 — guards fixing guards (39/371 commits; `feat` = 8 of 160)

**Cause:** `backlog-next.py` ranks problems -> enhancements -> features. A failing guard is always
a "problem", so scaffolding work always outranks product work. There is no quota.
**Fix:**
1. Category quota in `backlog-next.py`: at most N of every M picks may be
   guard/test-guard/ratchet/allowlist-scoped; the remainder must be product.
2. Apply the existing "stuck after 3 attempts is an escalation" rule to guards themselves — a
   guard amended 3+ times gets rewritten or deleted, not patched a 4th time.

## P4 — 11-way i18n fan-out (374 file-touches / 30d) and `api.ts` (55)

**Fix:**
1. `scripts/i18n_add_key.py <key> <english>` writes all 11 locales in one invocation
   (translate, or write `__MISSING__` plus one tracking issue). PRs then touch one tool call.
2. `types/generated/api.ts` is generated — regenerate it in pre-commit instead of hand-editing and
   committing it 55 times.

**Also removes** the single largest merge-conflict surface across parallel branches.

## P5 — 73 CI runs on one branch

**Cause:** `pre-merge-validate` exists as a skill but nothing enforces it; verification happens on CI.
**Fix:** `PreToolUse` matcher on `Bash(git push)` that runs the guard subset matching the branch's
changed paths and refuses a red push. Minutes locally against 73 remote runs.

## P6 — 90 branches in flight, 1 open PR

**Cause:** the WIP limit exists only as prose. Nothing counts worktrees.
**Fix:** `PreToolUse` on `Bash(git worktree add)` that counts `.worktrees/*` and denies past a cap
(suggest 8) with "land one first". Mechanical version of a rule the docs already state.

## P7 — 157 of 160 PRs close exactly one issue

**Fix:** `backlog-next.py --batch` returns a *cluster* of issues sharing a file family instead of
the single head; `batch-implement` already accepts multiple numbers, and `CLAUDE.md` already allows
`Closes #A, #B`. The i18n, guard, and test-guard families are ready-made clusters.

## Order to do them in

| Order | Fix | Why first |
|---|---|---|
| 1 | **P6** worktree cap | stops the bleeding — no new parked branches |
| 2 | **P1** drain parked | recovers the 401-commit inventory the cap now forces you to face |
| 3 | **P2** derived governor rate | makes the backlog able to shrink at all |
| 4 | **P5** pre-push gate | cheapest large win; removes CI thrash |
| 5 | **P4** i18n + api.ts tooling | removes per-PR drag and the conflict surface |
| 6 | **P7** clustered picks | raises value per unit of PR overhead |
| 7 | **P3** guard quota | policy call — needs your decision on the product/scaffolding split |

P6+P1 are one loop: the cap forces closure, the drain supplies what to close.

---

# Part 3 — What was implemented (2026-08-29)

## Correction to Part 1

The parked-work figure in Part 1 (**401 commits on 91 branches**) was wrong: it counted branches
whose PR had already merged, whose extra commits are rebase leftovers, not unlanded work. Measured
correctly by `drain-parked.sh`:

| | branches | unlanded commits |
|---|---|---|
| open PR | 1 | 5 |
| PR closed unmerged | 3 | 32 |
| **never had a PR** | **18** | **83** |
| **total genuinely parked** | **22** | **120** |

The pattern holds — 83 commits on 18 branches, several 17-23 days old, never reached a PR — but at
roughly a third of the size first reported.

## P6 — worktree ratchet cap  *(done, live)*

`~/.claude/scripts/worktree-cap.sh`, wired as a `PreToolUse` hook on `Bash` in
`~/.claude/settings.json` beside the backlog governor.

A flat cap of 8 against 92 live worktrees would have frozen all work, so the ceiling is a **ratchet**:
it seeds at the current population + 1 and can only ever descend (floor 8). Every branch that lands
permanently tightens the budget; nothing loosens it. `WORKTREE_CAP=<n>` pins it explicitly.

- Invocation detection reuses the governor's shlex command-position parser, extended to skip git's
  own value-taking options, so `git -C <path> worktree add` is caught and quoted prose is not.
- 7/7 detector tests pass; ratchet verified to descend (200 to 92) and never rise.
- **Currently at ceiling 92 / live 92 / headroom 0** — the next `git worktree add` is refused until
  something lands.

## P2 — governor threshold derived from closure  *(done, live)*

`~/.claude/scripts/backlog-governor.sh`.

The advisory stays advisory — `check` never blocks, and the comment at `:200-206` explains why
(blocking filing hides findings). What changed is the number, which was meaningless:

- `RATE_GREEN/AMBER/RED` constants replaced by factors applied to the trailing 7-day close rate
  (RED 1.0x, AMBER 1.5x, GREEN 2.0x). The old constants permitted 48/120/288 issues per day against
  a measured closure of ~31/day.
- `WINDOW` widened 1h to 6h. At ~1.3 closes/hour an hourly bucket could not express "match closure"
  in whole issues, and the integer floor silently rounded every verdict back up to 48/day.
- The advisory message now points at `drain-parked.sh` and `worktree-cap.sh status` — raise closure,
  rather than lower filing.

Live: `AMBER, threshold 12 issues / 6h, derived from 7d closure`. RED now lands at 32/day against
measured closure of 30.6/day.

## P1 — surface unlanded worktree branches  *(PRs open)*

**`~/.claude/scripts/drain-parked.sh`** *(done, live)* — ranks parked branches cheapest-first by
commits ahead, PR state, and file overlap with the base. Excludes merged-PR leftovers. Read-only:
never deletes, rebases, or pushes. `git merge-tree --write-tree` needs git >= 2.38 and this host runs
2.34, so conflict risk is approximated by counting files the branch touched that the base has also
moved since they diverged.

**AutoBot-AI #15294 / PR #15295** — `scripts/hooks/session-stop-orphan-check.sh` exited at its third
statement whenever it ran inside a worktree, so it never fired where work happens. It now reports
commits ahead of the PR base with no open PR, and does **not** file an issue for them: the branch is
already the record, and filing adds backlog without closure. Commits-ahead is the signal; a dirty
tree is an addendum, since a dirty tree alone fires on every Stop. 27 checks pass, 0 fail, 4 pending;
awaiting review.

**AutoBot-AI-Claude-dev-skills PR #1** — `/drain` step 1 said "drain the PR queue first", which with
1-2 open PRs and 22 parked branches pointed at the smaller queue. It now covers both and names the
parked one first. Merge state clean.

## Found on the way

**AutoBot-AI #15296** — the branch-switch guard in `.claude/hooks/block-dangerous-commands.sh:113-155`
denies correct commands three ways: it parses the whole shell line so a trailing `2>&1` becomes the
"branch argument" (defeating its own documented `git switch -` exemption); it ignores the `-C` target
so switches in unrelated repositories are blocked; and it matches the words inside quoted prose, which
blocked the filing of #15296 itself because the body quotes the command. `backlog-governor.sh` already
solves this class with shlex command-position detection.

## Still open from the plan

P5 (pre-push gate), P4 (i18n and api.ts tooling), P7 (clustered picks), P3 (guard quota).

---

# Part 4 — P5 retracted, and the skills-update gap (2026-08-29)

## P5 (pre-push gate) is WITHDRAWN — the premise was wrong

Part 1 read "73 CI runs on `issue-15238-path-roots`" as push-fail-push thrash. It was not.

```
runs: 100 | distinct head SHAs (pushes): 5 | workflows per push ~ 20
conclusions: {success: 82, skipped: 3, failure: 3, cancelled: 12}
```

Five pushes, each fanning out to roughly twenty workflow runs. Repo-wide the picture is the same:
**2 failed workflow runs out of the last 200**, both `Code Quality` on a single branch. There is no
push-fail-push loop to gate against, and CI is already fast (3.8 min median).

A pre-push gate would also have collided with the standing rule that the product's code is never
executed from the checkout — only static checks (grep guards, AST, lint) were ever eligible, and
those are already covered by pre-commit.

**What the number actually shows** is CI fan-out: ~20 workflow runs per push. That is compute cost,
not developer latency, and it is a different question from velocity. Not pursued here.

Revised order for the remainder: **P4 → P7 → P3.**

## The skills update gap (found by inspection, now fixed)

Merging PR #1 did not change the skill Claude actually reads. Three paths exist, and only the third
is live:

```
marketplace clone (refreshed):  ## 1. Land what is already finished, before starting anything
live plugin cache:              ## 1. Drain the PR queue first
```

`claude plugin update` reported "already at the latest version (1.0.0)" and did nothing, because the
version was unchanged. **A merged skill change is inert until the plugin version is bumped.**

Fixed in AutoBot-AI-Claude-dev-skills PR #2 (merged `27f2d13d9e`): version 1.0.0 to 1.0.1 in both
`plugin.json` and the `marketplace.json` entry, which must agree. The same PR corrected the
marketplace description, which claimed 12 skills and listed 11 (`batch-implement` was missing;
the tree has 12).

After the bump, `claude plugin update` moved 1.0.0 to 1.0.1 and the live cache now carries the new
text. `settings.json` came through intact — 14 keys, `enabledPlugins` still a dict, permissions and
hooks preserved, the worktree-cap hook still wired — so the documented array-rewrite gotcha did not
fire. **Takes effect on restart.**

---

# Part 5 — Final state (2026-09-01)

Parts 1 and 2 carry figures that later measurement corrected. **Read Part 3's correction and this part before acting on any number above.**

## The parked-work figure was wrong twice, and the truth is smaller again

| Reported | When | Basis |
|---|---|---|
| 401 commits / 91 branches | Part 1 | counted branches whose PR had already merged — rebase leftovers |
| 120 commits / 22 branches | Part 3 | excluded merged-PR branches |
| **1 genuinely orphaned branch** | here | full per-branch triage |

The scheduled sweep's first run reported `conflicted=32`. Triage of all 32:

| Group | Count | Truth |
|---|---|---|
| PR merged, ahead-commits are rebase artifacts | 12 | disposable — deleted after verifying merge commits were ancestors of base |
| PR closed deliberately | 8 | disposable — 7 deleted, 1 held by a live worktree |
| `release/changelog-*` | 12 | **not abandoned work at all** — a broken release step (#15376) |
| Never had a PR | **1** | `feat/gantt-timeline-view`, superseded |

**So the "parked work" that framed this whole investigation was mostly bookkeeping, not lost effort.** The automation reporting `updated=0` was accurate: 31 of 32 branches should never have merged into the integration branch, and no tool could know that.

## What the session actually changed

| Area | Outcome |
|---|---|
| Worktree ceiling | 92 → 9 (ratchet, floor 8) |
| `main` | 10 days / 519 commits stale → current; `v0.8.0` released |
| Changelog archive | 1 fragment → 14; index 0 → 13 versions; CHANGELOG 0 → 16 sections |
| CI placement | 3 jobs moved to self-hosted runners |
| Backlog governor | fixed constants → derived from trailing closure |

## Corrections worth carrying forward

- **P5 (pre-push gate) was withdrawn** — its premise was wrong. "73 CI runs" was 5 pushes x ~20 workflows, not thrash. Repo-wide, 2 of 200 runs failed.
- **Discovery-outruns-delivery held up.** Filing still exceeds closing; the governor now measures it honestly rather than against a constant that permitted 48/day against ~19/day of closure.
- **P4 (i18n 11-way fan-out) was never addressed.** Still 374 file-touches/30d across 11 locale files. It remains the largest untouched item from Part 2.

## Open, with owners

| Issue | Blocked on |
|---|---|
| #15306 drift | one clean run with a mergeable candidate |
| #15309 watchdog | host install on the two runner machines |
| #15376 changelog | a repository setting — Actions cannot open PRs |
| #15407 runner queue | decision: revert one job to hosted, or land #15392 |
| #15408 openvino parity | 7 files restate one floor |
| #15409 `calibrated_under` | shipped unwired; blocked by a 600/600-line file |
| #15410 marker-tests | no schedule, so perf regressions surface only on release PRs |

## Method notes for whoever picks this up

- **`git diff base...branch` cannot tell you a branch is stale.** It shows what the branch added since diverging, never that base moved past it. Rebase and read the conflicts instead. This produced a wrong call on `fix-dep-14439`.
- **A merged PR is not proof its branch is disposable, and a closed PR is not proof it was abandoned.** Both need the closing comment read. Twelve "conflicted" branches turned out to be a broken release step.
- **CodeQL flags validators.** Three separate times it flagged the code doing the checking. Where the shape allows, restructure so the tainted value never reaches the sink; where it does not, the alert needs dismissing.
- **A timeout that fires on queue time reads as "too slow"** and invites raising the bound, which cannot help.
