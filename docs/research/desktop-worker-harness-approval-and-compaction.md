# Desktop worker-agent harness — approval seams, compaction, and outbound governance

**Date:** 2026-08-13
**Source:** a public, permissively-licensed desktop AI worker application — Python agent
server, web-tech desktop shell, native voice sidecar, ~25 connectors, MCP client, and a
multi-provider LLM router. Weeks old at the time of reading, with a large open-issue count.
Repo name, author and locating metadata (star/fork counts, creation date) are withheld per
the no-external-names rule for committed docs; together they identify the repository as
surely as the name does. The URL was supplied in-session.
**Scope read:** the architecturally distinctive modules only — the permission engine, the
risk classifier, unattended mode, context compaction, the web guard, the connector gateway,
inbox routing, self-wake, and workspace trust. **Not** read: the GUI, packaging, provider
adapters, test suite. Source paths below are given by module name without the package
prefix, for the same reason as above.
**Method:** the source is not adoptable as code — desktop-single-user deployment shape, a
competing provider abstraction, and no stability record — so only *designs* were considered.
Every candidate was checked against our own code before a verdict was written; capabilities
we already have are recorded under "What we already do better" and were deliberately **not**
filed. AutoBot paths are repo-relative and line numbers are against `Dev_new_gui` at
`58bfba856`.
**Filed as:** #14065, #14066, #14067, #14068. Design input on #13416, #13250 (which also
gained a `needs-decision` label from this audit) and #13709. Back-links on #14028, #13421,
#14029.
**Prior art:** [[agent-harness-guard-and-context-audit]] (2026-08-11) audited a *different*
source (JVM stack) and filed #14027–#14031. Its findings on context sizing (#14029) and
gateway ingest (#14028) touch the same seams as this audit; both were reconciled against
rather than re-filed.

---

## Source analysis

### What it is

A local-first desktop application that runs an agent loop on the user's own machine and
produces finished deliverables — documents, sent replies, calendar entries — rather than
chat turns. Three layers: a native shell, a Python agent server exposing an HTTP/websocket
API, and an integration layer of connectors plus MCP client support, local files, and shell.
Multi-provider by design, built on a unified-LLM-API library with adapters for the major
providers and a router. Fast-moving and pre-stable: the designs are ahead of the evidence.

### Architecture

A single Python package with a flat module namespace (~35 top-level modules) and a handful
of subpackages for agents, tools, connectors, providers, memory, MCP, automation, skills,
personas, web and server. Not layered — module count carries the structure, not directories,
and a "large state management layer" in the server package is already a visible liability.

An agent-type registry sits over four concrete agents; personas are a separate
markdown-manifest layer on top. A tool registry exposes files, git, search, shell, plan,
todo, ask and subagent, with connector tools and MCP tools merged into the same surface.
**A permission engine sits between the agent loop and every tool call** — the architectural
centrepiece. Two independent human-in-the-loop channels exist: inline approvals, and an
inbox that mirrors questions to chat platforms and resolves them from replies. Four surfaces
(desktop GUI, TUI, CLI, chat platforms) run over one server.

### Notable implementation details

**1. Risk classification separated from policy.** The risk module reduces every tool to one
of four classes — `READ` / `WRITE_LOCAL` / `EXEC` / `EXTERNAL` — via a `classify()` cascade:
user overrides → a hardcoded map of vetted tool names → the tool's own `requires_approval`
metadata → default `READ`. The permission engine then applies *policy* to the class. A new
connector tool is `EXTERNAL` by default without anyone editing the policy engine.
`EXTERNAL` is explicitly the class that "leaves the machine".

**2. Five permission modes, not a boolean.** `DISCUSS` / `PLAN` (both read-only),
`INTERACTIVE`, `AUTO`, `CUSTOM`. `evaluate()` returns a `Decision{allowed, reason,
needs_user, rule}` — the `reason` and `rule` fields make the audit log a by-product of the
decision rather than a separate logging concern.

**3. Approval memory at three scopes.** Config allowlists (startup), session allowlists
(this run), and *task-scoped standing rules* mapping tool → approved targets, re-read on
every check. The third is the interesting one: "yes, for this file, for this task" is a
first-class object that expires with the task instead of leaking into the session.

**4. Shell allowlisting that resists prefix-bypass.** Commands are `shlex.split()` and the
allowlist entry's own tokens must be an exact *argv* prefix — not a string prefix. Any shell
metacharacter disqualifies the command from allowlist matching outright, so
`git status; rm -rf /` cannot ride in on a `git status` allowance.

**5. Workspace trust as a path-scoped capability grant.** A repo may declare its own allowed
command prefixes in a repo-local config file, but they are inert until the user trusts that
canonical path. Trust is path-based rather than content-hash-based — a deliberate usability
trade — persisted `0o600` with atomic replace.

**6. SSRF guarding with connection-level IP pinning.** Blocks loopback, link-local
(explicitly the cloud metadata endpoint), RFC1918, CGNAT, multicast and reserved ranges,
then defeats DNS rebinding by pinning the connection to the validated IP. Every redirect hop
is re-checked, bounded at 5. The framing is correct and worth restating: a model-chosen URL
is untrusted input, and a page that talks the agent into fetching the metadata endpoint
turns a read-only research tool into a probe of the machine's own network position.

**7. Compaction that never summarizes user messages.** Trigger at
`min(threshold_pct × context_window, cap_tokens)` — 80% and a 250K cap, so large-context
models compact *before* the quality cliff rather than at the nominal limit. The newest 25%
of the trigger budget is kept verbatim and the boundary snaps to a turn start, preferring
user-message boundaries. Older history is replaced by an LLM summary **plus a mechanically
extracted state block** — files written, recent shell commands with exit status, artifacts
produced, tools used — deterministic, no inference. All user messages survive mechanically,
capped at the 40 most recent so repeated compaction cannot grow them without bound. Tool
results are clipped to 400 chars on the theory that a file read 40 turns ago is better
re-read. The persisted transcript is untouched; only the *outbound view* is compacted.

**8. Unattended mode separates "where the human is" from "what the agent may do."** A
per-session flag routes anything that would prompt inline into the inbox and suspends the
agent until answered — and explicitly does **not** raise the autonomy ceiling, which stays
with the permission mode. Most harnesses conflate "nobody is watching" with "allow more";
this one does not.

**9. Inbox with bidirectional token correlation.** Items carry an embedded correlation token
when mirrored to a chat platform; the resolver parses the token plus an allow/deny intent to
resolve the item and resume the suspended agent. In-app is always the store of record;
external channels are mirrors. Routing is per-session override > persona default > global
default inbox.

**10. Self-wake.** Timer, job-completion and event triggers with a wake store
(`PENDING` → `DUE` → `FIRED`) turn an always-on agent into an event-driven suspend/resume
one at near-zero idle cost. **This module carries no wake-count, budget or recursion limit.**

### Strengths

The permission/risk split is well-factored and is the thing most agent harnesses get wrong:
policy, classification, trust grant and approval memory are four separate concerns in four
separate places. Security thinking is concrete rather than performative. Compaction's
mechanical state extraction alongside the LLM summary is a real idea — it makes the
compacted view robust to a bad summarization turn. Four surfaces over one server, with the
gateway handling only inbound and outbound going back through a normal send tool, is a clean
asymmetry that keeps outbound inside the permission engine.

### Weaknesses

Weeks old with a large open-issue count and no independent security review — nothing here is
production-proven. The flat module namespace is already a maintainability liability.
Self-wake is ungoverned. **Risk classification fails open**: a tool that is neither in the
hardcoded map nor annotated silently defaults to `READ`, in a system whose entire safety
story rests on classification. Workspace trust being path-based means trusting a repo trusts
all its future contents, including a pull that adds command prefixes. Gateway error handling
is permissive by design, so a silently non-connecting adapter looks exactly like a
configured one. No retrieval/RAG, no evaluation harness, no multi-tenancy — it is
single-user desktop software.

### Visible vs hidden metrics

**Visible (advertised):** connector breadth; multi-provider support including local models;
signed desktop builds with auto-update; approval-gated writes and sends; scheduled
automations with transcripts; chat-platform operation; local-first privacy; a permissive
licence; very high community interest. *All self-reported* — no independent benchmark,
security audit, or third-party evaluation, and the repo is weeks old.

**Hidden (inherited by an adopter):**

- *Stability tax:* a weeks-old codebase with hundreds of open issues means any code-level
  adoption is a fork you maintain, not a dependency you track.
- *Framework coupling:* the agent engine is built on a specific unified-LLM-API library;
  adopting its agent code means adopting that library's provider abstraction, which competes
  directly with an existing provider registry.
- *Desktop-shaped assumptions:* single user, local filesystem, one workspace at a time, a
  human at the machine. A server-side multi-user platform inherits none of that for free —
  every "user state dir + JSON file" store here becomes a per-user table elsewhere.
- *Surface sprawl:* four surfaces is four UX contracts to keep in sync.
- *Ops load:* self-wake, scheduler, inbox mirroring and the connector fleet are four
  independent background systems, each with its own failure mode and none with a visible SLO.

**Weighing.** For anyone wanting *the product*, the visible wins are real and the hidden
costs are the normal cost of young software. For a mature server-side platform, the hidden
costs veto adoption of the **code** almost entirely. What survives is a small set of
**designs** whose value is independent of the codebase: the risk-class/policy split,
argv-prefix shell allowlisting, connection-pinned SSRF guarding, compaction with mechanical
state extraction, and the unattended/autonomy separation. Those are cheap to re-implement
and carry no coupling. Everything else is either already solved here or costs more than it
returns.

---

## What we already do better

**1. SSRF guarding — we are strictly ahead.** `autobot_shared/security/ssrf_guard.py` does
everything the source's web guard does (public-IP assertion, connection pinning via a custom
`aiohttp` resolver at `:83`, per-hop redirect re-validation at `:265`, `max_redirects=5`)
**plus two things the source has not got:** `_CREDENTIAL_HEADERS` (`:139`), a 30-entry
explicit list stripped when a redirect crosses origin (#13624), so a 302 to an
attacker-controlled *public* host cannot harvest an `Authorization` or `x-api-key` header —
per-hop IP pinning does nothing about this case; and `_method_for_hop` (`:219`), fetch-spec
301/302/303 method rewriting with `_BODY_HEADERS` dropping, so a POST that redirects does not
silently replay its body.

**2. Command risk is argument-aware, not just argv-prefix.** The source rejects shell
metacharacters and requires an exact argv-prefix match. That is the floor.
`autobot-backend/secure_command_executor.py` does that (`shlex.split` at `:148`, `:254`)
**and** elevates on argument *shape*: `_DOCKER_ESCAPE_FLAGS` (`:91` — `--privileged`,
`--net=host`, `-v /:`, `--security-opt=seccomp=unconfined`), `_FIND_SUID_RECON_PATTERNS`
(`:111`), `_DNS_RECON_COMMANDS` (`:122`), and an env-var-prefix hijack list covering
`LD_PRELOAD`, `PATH`, `IFS`, `BASH_ENV`, `PROMPT_COMMAND` and `SHELL` (#7406 —
`SHELL=/bin/sh; sudo -E sh` is a real escalation chain). Five risk levels with `_RISK_ORDER`
(`:126`) picking the strictest across chained sub-commands. A base command that is
allowlisted can still be blocked on its flags; the source's model cannot express that.

**3. Structural invariants on the tool classification, enforced at import.**
`autobot-backend/chat_workflow/code_exec/tool_policy.py` declares three invariants —
`readonly ⊆ injectable`, `sensitive ∩ injectable = ∅`, `mutating = injectable − readonly` —
and `_check_invariants()` (`:90`) raises at import if a future edit breaks one.
`derive_views` (`:62`) subtracts `SENSITIVE_TOOLS` from the env-supplied injectable set
unconditionally, so an operator widening an env var **cannot** make `execute_command`
shimmable. The source's classification map has no invariant and no fail-fast.

**4. Guard posture is a named profile, and approval is on by default.**
`autobot-backend/agent_loop/guard_profile.py` gives `minimal` / `standard` / `strict` across
five guards at once, with per-guard env overrides that win over the profile (`:73`).
`require_approval_for_sensitive` defaults `True` (`agent_loop/types.py:238`). The source's
permission modes cover the human-facing dimension but bundle nothing else.

**5. An adversarial pre-action verifier runs before the human is asked.**
`agent_loop/loop.py:1656` — `_run_verifier` (#10547) attempts to refute the tool call, then
either hard-blocks or escalates to the human *with the refutation rationale attached*. No
counterpart in the source; its approval prompt carries only the tool and its arguments.

**6. Per-agent identity boundaries.** `forbidden_work` manifests resolved through
`orchestration/agent_registry.py` and hard-blocked at `loop.py:1691` `_check_forbidden` —
enforcement keyed to *which agent* is acting, not just which tool. The source has one global
policy per session.

---

## Findings and where they went

### Filed

| Issue | Finding | AutoBot evidence |
|---|---|---|
| #14065 | Summarization failure returns a success-shaped placeholder; `reset_session` runs anyway; the status dict reports `summary_created: True` | `chat_history/context_overflow.py:277-280`, `:443-461`, `:407-418` |
| #14066 | Compaction splits at `len(messages) // 2` — no turn boundary, no user-message preservation, no deterministic state block | `chat_history/context_overflow.py:450-452`, sanitizer applied only to summarizer input at `:251` |
| #14067 | Gateway outbound sends cross no approval seam | `services/gateway/gateway.py:219-260`; 0 approval hits across 19 files (positive control: 19 files match `def `) |
| #14068 | Approvals can only be answered at the screen; "nobody is watching" is only expressible by lowering the guard profile | `chat_workflow/tool_handler.py:1312`, `agent_loop/types.py:239`, `guard_profile.py:48-50` |

**#14065 and #14066 are ours, not the source's.** They were found while auditing our
compaction path against theirs; neither defect exists in the source. The most valuable
output of a comparative audit is often not the thing you adopt.

### Routed to existing issues rather than filed

- **#13416** (differential test across approval planes) — it scopes *two* planes; there are
  **four**: `tool_catalogue.py:63` `SENSITIVE_TOOLS` (prefix), `tool_catalogue.py:82`
  `APPROVAL_CATEGORY_TOOLS` (word-boundary prefix), `code_exec/tool_policy.py:36` (exact),
  `secure_command_executor.py:271` `CommandRisk` (argv + argument shape). Differencing plane
  1 against plane 3 atom-by-atom, these are in `SENSITIVE_TOOLS` and reachable through **no**
  approval category: all of `FILE_WRITE_TOOLS`, `terminal`, `system_exec`, `ansible`, `helm`,
  `git_reset`, all of `HTTP_WRITE_TOOLS`, `code_interpreter`. Note `destructive operations`
  covers `FILE_DELETE_TOOLS` but **not** `FILE_WRITE_TOOLS` — a work item can declare
  approval-before-destructive-operations and still have the agent overwrite a file
  unprompted. Two of the gaps are documented as deliberate at `tool_catalogue.py:79-81`; the
  file-write one is documented nowhere, which is the difference between an asserted decision
  and drift.
- **#13250** (tool approval gated twice) — partial static answer to its open "can any flow
  reach execution with neither gate firing" question. Path A fail-opens twice:
  `AUTOBOT_CHAT_APPROVAL_GATE` reads as `False` when unset
  (`chat_workflow/session_role.py:34`), and `_tool_call_needs_approval`
  (`chat_workflow/graph.py:494`) returns `False` whenever no categories are declared. A third
  route to the same place: a declared category outside the valid set matches no tools and
  silently disables the gate (`tool_catalogue.py:90` docstring). Labelled `needs-decision`
  for the one question the code cannot answer — whether the default-off flag is a staged
  GH#11202 rollout or an oversight, which changes whether flipping it is separable work or
  the last step of the convergence.
- **#13709** (approval memory scope key) — it generalises the scope *key*; the missing axis
  is *duration*. `services/approval_memory.py:244` offers one persistent grant (30-day TTL,
  per-user per-project, `:17`) and the alternative is not remembering. Adding mail, browser
  and signup domains to a key whose only lifetime is 30 days widens grants silently; a
  task-scoped standing rule recording approved *targets* is the missing third scope.

### Deliberately not proposed — do not re-file

- **Unifying the four classification planes.** They use prefix / word-boundary / exact
  matching respectively, and `tool_policy.py:23-26` documents its split from the agent-loop
  plane as deliberate. A merge changes matching semantics at three security seams at once to
  buy "no tool is unclassified" — which the #13416 test buys at a fraction of the blast
  radius. **Rejected by hidden metrics**; the coverage test is the correct form of the idea.
- **Self-wake.** The source's implementation has no wake-count, budget, or recursion limit.
  We have Celery scheduling plus `autobot_shared/leader_lease.py`; adding agent-initiated
  resumption would require extending the loop-guard discipline to cover it, and the visible
  win — near-zero idle cost — is a desktop concern, not a server one.
- **Repo-declared, user-trusted command allowances.** We have no workspace-trust equivalent
  (`grep -rln "workspace_trust|trusted_workspace|trust_store"` returns zero). Low value for a
  server platform, and the source's own version is path-based, so a pull silently extends the
  grant. Adopt the shape, not the trust semantics, if ever.

---

## Verdict

The source is weeks old and its code is not adoptable at any point. What survived the
weighing: one implementation idea (mechanical state extraction in compaction, #14066), one
coverage gap it made visible (connector sends cross no approval seam, #14067), one design
separation worth copying (remote human ≠ more autonomy, #14068), one default-posture
question for the owner (#13250), and one architectural idea our own hidden costs veto in
favour of a test (#13416).

**Confidence:** high on the AutoBot side — every claim is a file read at a cited line, and
the one absence claim (#14067) was verified with a positive control. Medium on the source
side — fetched summaries of ten modules, not full file reads. One correction during the
audit: the first pass named `HTTP_WRITE_TOOLS` as the notable approval-category gap;
differencing all atoms found six more, and `FILE_WRITE_TOOLS` is the worse one.
