# AutoBot Development Instructions

Index plus the rules that are catastrophic to miss. Everything else is in `docs/developer/` —
read a doc when its trigger fires, not before. Universal rules (worktree mandate, evidence, never-idle) live in the
global instructions and are not repeated here; where the two disagree, **this file wins**.

## Read when triggered

| Trigger | Doc |
|---|---|
| Starting a task — the 8 core rules in full | [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) |
| Branching, worktree collisions, stashing, force-push, push recovery | [`CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md) |
| Labels, `gh` workarounds, deployment, pre-merge gates | [`CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) |
| Batching issues, or opening, pushing, reviewing or merging a PR (incl. the required body headings) | [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) |
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

- **Before acting on a measurement, name what it is about** — environment, path, symbol, question. Family **F** (*correct, complete, about a different question*) reads as a clean answer: if more data would not change it, it is F → `MEASUREMENT_DISCIPLINE.md`.
- **Say "I don't know" — never fabricate.** A guessed cause, count or verdict is the one error treated as serious; an admission is an opening, not a closure → [`MEASUREMENT_DISCIPLINE.md`](docs/developer/MEASUREMENT_DISCIPLINE.md#a-stated-gap-is-a-finding-never-a-closure).
- **PRs target `main`; `release` is the release branch.** `release`/`master` are blocked by the pre-commit hook — use `issue-*` or `hotfix-*`.
- **Never work from a stale base.** `git fetch origin` and branch from current base before the first edit; answer "is this already done?" against current `origin/main` and the issue's ACs, **never an old branch** → `CLAUDE_GIT.md`.
- **Commit format:** `<type>(scope): <description> (#issue-number)`. Never `--no-verify` — a PostToolUse hook auto-formats `.py`.
- **Never hardcode.** Config via SSOT, TTLs via env-var-backed module constants, no IPs or ports in code.
- **The codebase is the source of truth** — never edit `/opt/autobot/` or `/var/log/autobot/`.
- **System updates (test AND prod) go through the builtin updater only** — the code-sync API / self-update path a user reaches in the maintenance UI. If the builtin cannot do it, fix that gap (issue + PR); never side-channel via ad-hoc ansible or shell.
- **No agent cleans up data or credentials on its own.** Deleting, rewriting or rotating stored data or credentials is only *proposed* by an agent. A human approves it through an always-available review queue (the approval gates), it is never auto-approved, and it always leaves a durable paper trail — [#17038](https://github.com/mrveiss/AutoBot-AI/issues/17038).
- **Security reviews are findings-first** — one-line verdict, then a severity/`file:line`/issue/fix table, within 3 tool calls. Verify *after*; never explore before the verdict lands. Skill: `secreview`.
- **Nothing internal in outward artifacts** — no IPs, hostnames, secrets, tokens, or internal filesystem paths in issues, PRs, comments or logs. Redact to a generic role or node reference.
- **Open-PR cap:** `AUTOBOT_OPEN_PR_CAP` (default 40), enforced at pre-push for new branches — at the cap, finish, merge, or close before starting new work; every PR still gets a `code-reviewer` pass before merge.
- **Same file ⇒ ONE PR, ONE agent** — check the open PRs touching a file before editing it; batching, append-before-open and the sweep point → [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md#pr-granularity).

## When rules conflict

Rules here accumulate; some pull against each other. **Precedence, highest first:**

1. **Safety and disclosure** — nothing internal in outward artifacts, no agent deletes data or
   credentials, never edit `/opt/autobot/`. These never yield to throughput.
2. **The newer, more specific instruction** over the older, more general one. An owner rule dated
   today outranks a standing rule; a rule naming this PR outranks a rule about PRs. Say which one
   you applied when they disagree, rather than picking silently.
   *Scope:* this orders rules **that already apply**. It does not re-open which file wins — the
   project-over-global precedence stated at the top of this file is settled first, and a newer
   global rule does not override this file by being newer. Where a global rule is newer **and**
   this file is silent, there is no conflict and it simply applies.
3. **Evidence rules over process rules.** A tick needs code evidence even when ticking would close
   a thing the process wants closed.
4. **Everything else**, in the order it appears.

**PR-granularity conflicts** (same file vs same scope vs append) → [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md#pr-granularity).

**Known conflict, unresolved by design:** *finish everything* and *one PR's CI at a time* cannot
both hold at a queue depth above one. Serialization wins while it is in force; the completion goal
becomes *nothing mergeable left unmerged, nothing merged left uncleaned*, which is checkable at any
instant. A goal phrased as "no work in flight" has no reachable end state in a repo with running CI
and will read as permanent failure.

## Git/PR Workflow

### Pre-Push Checklist (non-negotiable)
1. No file exceeds `MAX_LINES` (600, enforced by `check_python_file_size.py`) — split, don't
   raise the ceiling; see [`RATCHET_BASELINES.md`](docs/developer/RATCHET_BASELINES.md).
2. Run the repo's lint/type-check locally before pushing — don't rely on `/pre-merge-validate`
   at review time to catch it first.
3. Never bypass pre-commit hooks via `core.hooksPath` (`--no-verify` is under **Never violate**).

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
