# AutoBot Development Instructions

Index plus the rules that are catastrophic to miss. Everything else is in `docs/developer/` —
read a doc when its trigger fires, not before. Universal rules (worktree mandate, issue
decomposition, evidence, model tiers, never-idle) live in the global instructions and are not
repeated here; where the two disagree, **this file wins**.

## Read when triggered

| Trigger | Doc |
|---|---|
| Starting a task — the 8 core rules in full | [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) |
| Branching, worktree collisions, stashing, force-push, push recovery | [`CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md) |
| Labels, `gh` workarounds, deployment, pre-merge gates | [`CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) |
| Opening, reviewing, or merging a PR (incl. the required body headings) | [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) |
| Closing an issue | [`CLAUDE_CLOSURE.md`](docs/developer/CLAUDE_CLOSURE.md) |
| Running parallel agents or a batch | [`CLAUDE_BATCH.md`](docs/developer/CLAUDE_BATCH.md) |
| Need a service, port, or architecture fact | [`AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md) |
| Adding an event type, WebSocket route, bus, or session state | [`EVENT_STATE_DOCTRINE.md`](docs/developer/EVENT_STATE_DOCTRINE.md) |
| Reviewing or changing path validation, session ownership, plugin loading, or secrets | [`THREAT_MODEL.md`](docs/developer/THREAT_MODEL.md) |
| Adding a redactor, adding a detector to one, or picking which redactor to call | [`REDACTION_BOUNDARY.md`](docs/developer/REDACTION_BOUNDARY.md) |
| Adding or bumping a HuggingFace `from_pretrained` call site | [`MODEL_REVISION_PINNING.md`](docs/developer/MODEL_REVISION_PINNING.md) |
| Claiming a work scope, adding a lock/lease, or any "which agent owns this" state | [`AGENT_COORDINATION.md`](docs/developer/AGENT_COORDINATION.md) |
| Deviating from a standard pattern on purpose | [`ARCHITECTURE_EXCEPTIONS.md`](docs/developer/ARCHITECTURE_EXCEPTIONS.md) |
| Adding a ratchet, changing its detector or matcher, or freezing/regenerating a baseline | [`RATCHET_BASELINES.md`](docs/developer/RATCHET_BASELINES.md) |
| Writing or changing a guard, sweep, count, or acceptance criterion — or reading an empty result | [`MEASUREMENT_DISCIPLINE.md`](docs/developer/MEASUREMENT_DISCIPLINE.md) |
| Before pushing any code change — known self-inflicted bug patterns | [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md#self-review-before-pushing-known-self-inflicted-patterns) |

## Engineering Standard

Correctness → Speed → Maintainability. No wasted motion, no speculative work.
Parallelize independent calls · minimal surface area · async-first · ≤3 exploration commands
then act.

**The 8 core rules** — full text in [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md):
1 Check before writing · 2 Reuse from `autobot_shared/` · 3 Standardize (≤30-line functions,
no `_v2`/`_fix` suffixes) · 4 Clarify ambiguous architecture before coding · 5 Verify with
evidence · 6 Report **and fix** every discovered problem · 7 Grep the *behavior*, not the
symbol, on extraction PRs · 8 Outbound HTTP goes through the guarded fetch (egress policy).

## Never violate

- **Say "I don't know" — never fabricate.** But an admission is not a closure — it is an opening: it means *"I need help, let's find this together"*, so **ask right then** in an interactive session, and where there is nobody to ask leave the criterion unticked, file it, and never drop it. A *stated* gap is a finding; an *unstated* one is the defect. A guessed cause, count or verdict is the one error treated as serious — for an agent a wrong answer is not an opinion, it executes. "I could not determine X" is a contribution. Guards and reports distinguish *nothing found* from *did not look*. See [`MEASUREMENT_DISCIPLINE.md`](docs/developer/MEASUREMENT_DISCIPLINE.md).
- **PRs target `main`; `release` is the release branch.** `release`/`master` are blocked by the pre-commit hook — use `issue-*` or `hotfix-*`.
- **Never work from a stale base** — and the half that bites is the judgement, not the freshness. Answer "is this already done?" against current `origin/main` and the issue's acceptance criteria, **never against an old branch**: a stale answer points toward doing *more* work, so nothing pushes back on it, and reviving such a branch can regress newer code. `git fetch origin` and branch from (or rebase onto) current base before the first edit — the auto-update bot only refreshes branches that already have a PR, so the window this covers is everything before the first push.
- **Commit format:** `<type>(scope): <description> (#issue-number)`. Never `--no-verify` — a PostToolUse hook auto-formats `.py`.
- **Never hardcode.** Config via SSOT, TTLs via env-var-backed module constants, no IPs or ports in code.
- **The codebase is the source of truth** — never edit `/opt/autobot/` or `/var/log/autobot/`.
- **System updates (test AND prod) go through the builtin updater only** — the code-sync API / self-update path a user reaches in the maintenance UI. If the builtin cannot do it, fix that gap (issue + PR); never side-channel via ad-hoc ansible or shell.
- **No agent cleans up data or credentials on its own.** Deleting, rewriting or rotating stored data or credentials is only *proposed* by an agent. A human approves it through an always-available review queue (the approval gates), it is never auto-approved, and it always leaves a durable paper trail — [#17038](https://github.com/mrveiss/AutoBot-AI/issues/17038).
- **Security reviews are findings-first** — one-line verdict, then a severity/`file:line`/issue/fix table, within 3 tool calls. Verify *after*; never explore before the verdict lands. Skill: `secreview`.
- **Nothing internal in outward artifacts** — no IPs, hostnames, secrets, tokens, or internal filesystem paths in issues, PRs, comments or logs. Redact to a generic role or node reference.
- **Open-PR cap:** `AUTOBOT_OPEN_PR_CAP` (default 40), enforced at pre-push for new branches — at the cap, finish, merge, or close before starting new work; every PR still gets a `code-reviewer` pass before merge.
- **Batch same-scope issues into one PR by default** — one CI suite per batch, not per issue. Each issue must still be *fully* delivered; partial delivery never closes. Independent or different-risk changes get separate PRs, as does anything too large for one honest review pass. Write **one `Closes #N` per line** — `Closes #A, #B` links only #A.
- **Finish what you started — append before you open** (owner rule 2026-09-19). Before opening a new PR, check for an open PR the change can be appended to (same scope, risk, owner) and append; fix and land existing PRs before opening new ones; finish started issues before starting new ones.
- **Issues touching the same file go in ONE PR, solved by ONE agent** (owner rule 2026-09-18). Hub files — registries, ratchet baselines, `.secrets.baseline`, `.github/`, `CLAUDE.md` — are exempt; one agent may split sequentially, the next PR opening after the previous merges. Check the open PRs touching a file before editing it.
- **A pushed PR ends the tick — never wait on its CI.** Pushing is the sweep point: check every *other* in-flight PR once (approval gate, CI verdict, behind-ness), act on what is green or red, then start the next non-colliding scoped issue immediately. The PR just pushed is re-checked at the next sweep, never polled.

## Git/PR Workflow

### Pre-Push Checklist (non-negotiable)
1. Commit subject includes the issue reference — see commit format under **Never violate**.
2. No file exceeds `MAX_LINES` (600, enforced by `check_python_file_size.py`) — split, don't
   raise the ceiling; see [`RATCHET_BASELINES.md`](docs/developer/RATCHET_BASELINES.md).
3. Run the repo's lint/type-check locally before pushing — don't rely on `/pre-merge-validate`
   at review time to catch it first.
4. Never bypass pre-commit hooks via `core.hooksPath` or `--no-verify` — see **Never violate**.

## Verification

Never state CI is green, history was destroyed, work is complete, or a check failed without
pasting the command and its output. Three-dot diffs (`git diff base...head`, from the merge
base) for "what this PR changes" — a two-dot diff between two tips shows base's own
independent commits reversed as if the PR made them once base has moved. Re-read source APIs
for current numbers — never hand-patch a cached figure. Applies to every claim made against
[`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) and
[`CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) steps.

## Environment Guards

A worktree cap, protect-files hook, or permission classifier blocking an action is reported
with the exact blocker, verbatim, immediately — never retried blind and never resolved by
proposing to raise the limit. Never touch a branch, PR, or worktree another session owns,
unless the user asks or it is the abandoned/stale work you were dispatched to finish (claim
it in the ledger first) — see the global worktree-mandate exception.

## Issue Filing

Search open **and** closed issues (`gh issue list --search "<query>" --state all`) before
filing — no duplicates. Scrub external vendor/product names from filed content (see the
`research-to-issues` skill). Link children to their umbrella with native GitHub relationships,
not just the `- [ ]` checklist — full commands in [`CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md).

## Essential Patterns

| What | How |
|---|---|
| Redis | `from autobot_shared.redis_client import get_redis_client` |
| Config | `from autobot_shared.ssot_config import config` / `import { getBackendUrl } from '@/config/ssot-config'` |
| Logging | `from autobot_shared.logging_manager import get_logger` → `get_logger(__name__)` / `createLogger('Name')` — no `print()` or `console.*`; stdlib `logging` only where a config-mocking test harness forbids it (see `autobot_shared/user_management/password_epoch.py`) |
| Encoding | Always `encoding='utf-8'` explicitly |
| Cache TTL | Never hard-code — module-level constant from an env var (see `chat_history/cache.py`) |
| Store authority | Persisting a concept? `from autobot_shared.store_authority import system_of_record` — one store is durable, every other copy is a rebuildable projection |
| LEDGER/EXECUTOR | Coordination tools complete instantly — do NOT wait; continue immediately with execution tools |
| Copyright | `mrveiss` is sole owner and author |
