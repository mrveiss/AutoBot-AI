# Handoff: research/agentic-desktop-os-distribution (no branch — research-scope session)

status: complete (research); artifacts LANDED via PR #17472 (#17471)
pr: #17472 carries the documents and index rows; this session itself wrote no code and opened no branch
base_at_read: origin/main 4c9034782d
local_main_behind: yes — main tree sits at 2e00fa4a67, origin/main is 4c9034782d (fast-forward needed)
gates: n/a (no code change)
worktree: none created

## What this session did

Two-phase source research (an opinionated agent-native desktop OS distribution) + a full AutoBot
comparison, then a cross-reference of every finding against open **and** closed issues.

- Report: `docs/research/agentic-desktop-os-distribution.md` (345 lines) — **UNTRACKED**
- Index row added to `docs/research/_index.md` — **UNCOMMITTED**
- 7 issues filed, 6 pre-existing issues witnessed with comments. Full mapping is the last table in
  the report.

## ACTION REQUIRED — carry these artifacts onto the next branch you touch

Owner decision, 2026-09-25: **do not open a branch for the docs.** When you take a red PR to fix,
add these to that same branch alongside the fixes, then land them with it.

Files to carry (all currently untracked/uncommitted in the main tree at
`docs/research/`):

1. `docs/research/agentic-desktop-os-distribution.md` — this session's report.
2. `docs/research/layer-streamed-low-vram-finetuning-cli.md` — **a peer session's report, left
   untracked before this session started.** Carry it too: issue **#17420** ends with
   "Full analysis: `docs/research/layer-streamed-low-vram-finetuning-cli.md`", and that path does
   not resolve from base (`git show origin/main:docs/research/layer-streamed-low-vram-finetuning-cli.md`
   → fails), so the citation dangles until it lands. Do not edit its contents — it is not yours.
3. `docs/research/_index.md` — the working-tree diff carries **two** rows, one per doc above. Both
   belong to the same carry; do not split them from their docs.
4. `.session/HANDOFF-research-agentic-desktop-os-distribution.md` — this file. `.session/` is a
   tracked directory (11 files committed), so this handoff is untracked too and rides along with
   the same carry.

Best-fitting candidate branch: **PR #17427** (`worktree-issue-17420`, "stop passing
grant_capabilities= to loader that…"). It is red (4 failing checks), it touches
`autobot-backend/plugin_manager.py`, and it fixes the very issue that cites doc (2). Fixing that PR
is the natural moment to carry all three files. Any other red PR is acceptable if #17427 lands first.

## Issues filed this session

| Issue | Finding | Parent umbrella |
|---|---|---|
| #17459 | Plugin capabilities granted but never checked — `CapabilityChecker.check()` has zero call sites, so `GET /plugins/audit` cannot be non-empty | #17217 |
| #17460 | No plugin namespace reservation — a community plugin can claim a core plugin's name; only `plugin_dirs` ordering prevents the shadowing | #17217 |
| #17461 | Release channels specified in `docs/developer/AUTOBOT_REFERENCE.md:186-190`, unimplemented (only a `main`/`release` branch pin exists) | #10016 |
| #17462 | `./autobot setup` and `./autobot repair` exec scripts that do not exist; three unrelated start/stop/status paths | #10016 |
| #17463 | Three approval policies, one enforced — `needs_approval()` and the `minimal` guard profile have no production caller | #13413 |
| #17464 | A crash produces a log line only — no deduped failure→diagnosis trigger; `CausalInferenceEngine` instantiated at `grounded_agent.py:97-98` and never called | none (standalone) |
| #17465 | Out-of-band deployment mutation undetectable — the builtin-updater-only rule has no detector | #10016 |

All six parent links were recorded natively as sub-issues and read back.

## Batching constraints for whoever implements these

- **#17420, #17421, #17280, #17459, #17460 all touch `autobot_shared/plugin_sdk/` and
  `autobot-backend/plugin_manager.py`** → one agent, one PR (same-file rule). #17427 is already that
  PR's head start; append to it rather than opening another.
- **#17262 and #17465** share `ansible/playbooks/update-all-nodes.yml` + `api/code_sync.py` → likely
  one PR.
- **#17459 blocks an honest close of #17420.** #17420's body claims "capability enforcement itself
  exists and works"; it does not — `check()` is unreachable. A correction comment is posted there.
  Do not tick #17420's second acceptance criterion until #17459 is fixed.

## Witness comments posted (rediscoveries, not new repairs)

#17420 (with the correction above), #17421, #17280, #17262, #17219, #15030.

## Open-PR state at handover (12 authored by this account — NOT this session's work, reported only)

| PR | checks | note |
|---|---|---|
| 17447, 17442, 17429, 17395 | 0 FAIL, 0 pending | closest to mergeable; all `REVIEW_REQUIRED` |
| 17426, 17458 | pending (8, 10) | still running at handover |
| 17427 | 4 FAIL | the plugin PR above — red |
| 17456, 17439 | 2 FAIL each | |
| 17444, 17438, 17408 | 1 FAIL each | |

Red CI never merges — each red one needs a root cause, not a rebase. `mergeable` read `UNKNOWN` on
most of these; GitHub had not computed it, so re-poll before acting.

## Worktree inventory (13 live — inventory only, nothing swept)

One naming anomaly worth knowing before any lookup by directory name:
`.worktrees/issue-17339-husk-repair-ansible` has branch **`issue-17363-global-disclosure`** checked
out. Directory name ≠ branch name.

## Not done, deliberately

- **"One skill body shared across agent backends"** — the one source pattern left **unaudited**. It
  has no verdict in the report and no issue. It needs its own pass over
  `autobot-backend/services/execution/`; do not treat its absence from the findings as evidence it
  is fine.
