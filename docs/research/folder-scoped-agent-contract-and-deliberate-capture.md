# Research: folder-scoped agent contract + deliberate knowledge capture

**Date:** 2026-10-10
**Source:** a small hosted "shared thinking space" product from an early-stage vendor, plus its
MIT-licensed open protocol (spec, JSON Schema, reference TypeScript library, conformance kit) and
thin agent-surface adapters (a coding-agent plugin, a CLI, an SDK). Low adoption (single-digit to
low double-digit stars), protocol self-declared *provisional* at a v0.2x candidate, under daily
churn. Names and URLs withheld per the no-external-names rule; the URL was supplied in-session.
**Method:** read the landing page (client-rendered; read via a reader proxy), `llms.txt`,
`robots.txt`/`sitemap.xml`, the protocol README, `SPEC.md` (shape, maps, identity, local effects,
conformance), `SKILLS.md`, and the commit-trailer schema. Source code under `src/` was not read.
**Status:** Phases 1 and 2 complete (2026-10-10).
**Filed as:** #18162, #18167 under #18080 · #18163 under #16777 · #18164, #18165, #18166, #18168 under #13413. #18162 blocked by #18077.
**Untrusted content:** the site's `llms.txt` carries a "notes for automated readers" section; it is
descriptive metadata (content-negotiation and licensing headers), not an instruction. Nothing acted on.

---

## Source Analysis

### What It Is

A product that keeps an AI's working context as a git-tracked folder of Markdown rather than as
opaque "memory". The pitch: every AI conversation starts from zero; implicit memory banks
half-positions as conclusions. Instead, the agent *proposes* what is worth keeping, the person
edits/keeps/drops it, and the agreed result is committed. The hosted tier (~€7/month, early access,
plus pay-as-you-go credits) adds sharing (a note, a folder, or a whole space, to named people or a
link), access control and public spaces; the local integrations need only Node.js + git, no server,
vector DB or daemon. Maturity: early — the protocol is versioned provisional with one frame
("Foundation") frozen for compatibility while a successor frame ("Agreement") migrates in.

### Architecture & Key Patterns

- **One directory rule.** Non-underscore `.md` = knowledge; exact `_agent/` = how to work here;
  any other `_`-prefixed directory = opaque extension that base readers MUST silently ignore
  (`_assets/`, `_threads/` are the first standard extensions).
- **Fractal `_agent/`.** Can appear at any depth; contracts compose root → position, nearest wins.
  This is explicitly "instruction files grow up into a folder" — one big agent-instructions file
  degrades as it grows, so split it and load only the slice the task needs.
- **Two-tier loading.** Entry file (`agreement.md`) loads in full; every sibling loads at *summary*
  (frontmatter `summary:`) unless the entry declares it `context.full`. Skills load as
  name + description until selected (skill-manifest compatible `<name>/SKILL.md`).
- **Progressive disclosure everywhere.** Every position presents as *summary → surface (README) →
  children*; document inspection deepens *summary → outline (ATX headings) → one section → full*.
  "Stop at the first sufficient rung." No embeddings locally — structure is the index.
- **Prompt placement split.** Awareness items are tagged `head` (stable, cacheable) vs `tail`
  (volatile: git state, working tree, open change), rendered deterministically so two harnesses emit
  byte-identical output. Effectively a prompt-cache-friendly layout made normative.
- **Reference vs authority.** Reading another space ("focus"/"look") returns its context with
  `contractRole: reference` — read but never composed into the caller's own instructions. A
  structural defence against one space's instructions hijacking the agent.
- **Provenance in git, not metadata.** Author = person; agent = `Co-authored-by` trailer. Optional
  Change layer trailers: `Op:`, `Conversation:`, `Turn:`, `Change-Id: chg_<slug>-<rand>` — the same
  Change-Id stamped across every repo a decision touched, so `git log --grep` traces it. Adapted
  from a code-review tool's Change-Id, re-aimed from "across rebases" to "across repos".
- **Local-effects boundary.** Two write primitives — atomic `write_markdown` and `commit_paths`
  over an *exact* path set with *expected per-path blob revisions* (optimistic concurrency); no
  force, no implicit `-a`; gitignored paths refused; result is `ok | partial | error`, and a durable
  half-done effect MUST report `partial` with recovery guidance — never a claimed rollback.
- **Operating loop as skills.** arrive → orient → inspect → act → capture → push/pull → reflect;
  push and pull deliberately never collapsed into one "sync". *Reflect* = compare declared
  understanding against reality and propose a recalibration ("drift signal").
- **Stack:** TypeScript reference lib (npm), JSON Schema for frontmatter, JSON conformance vectors
  so other languages can conform.

### Notable Implementation Details

- **Absent-file-as-drift:** a named-but-missing `_agent/` file is surfaced as drift, never silently
  filled. Schema mismatch (`_agent/schema.md` for a collection's instance shape) is also drift,
  never a write rejection.
- **Ambiguity is a typed result, never a guess:** both entrypoints present → `contract_choice_required`;
  invalid `context.full` target (absolute, traversing, glob, symlink, missing) → `contract_invalid`
  rather than a partial frame. Unknown/ambiguous map address → typed result, never a path.
- **Per-agent private notebooks** at `_agent/<agent-id>/`, gitignored: agents read each other's,
  each writes only its own.
- **Shared vs local by `.gitignore`:** awareness can include local code repos and drafts; only
  committed content travels. A pointer into ignored content is flagged as dangling-for-others.
- **Access ladder vocabulary:** `view < read < history < copy < write < push < manage`, with map
  disclosure capped at `view` — the protocol defines words, the host enforces.
- **Identity:** an optional 96-bit `root_node_id`; clone keeps it, fork remints; a tool may only
  *propose* adding an ID, never mint/commit/rekey because the field is absent.

### Strengths

- Clear, small core rule (underscore = extension) with explicit forward-compatibility.
- Human-in-the-loop capture is the whole product — directly addresses "memory saved what I didn't mean".
- Deterministic, cache-aware context rendering; conformance vectors keep implementations honest.
- Honest failure semantics (`partial`, typed ambiguity results) — unusually rigorous for its size.
- Zero infra locally; data is plain markdown + git, trivially portable.

### Weaknesses / Limitations

- Provisional and churning fast (two coexisting contract frames mid-migration; "pin a version").
- Heavy bespoke vocabulary (position, surface, rung, placement, focus, look, map, handle) — the
  spec is ~34 KB plus ~15 schema docs for what is conceptually "folders of notes + instructions".
- No retrieval beyond structure locally; scales with how well the tree is curated, not with volume.
- Sharing/ACL/search only in the hosted tier; local mode is single-user git.
- Capture quality depends on the agent's judgment and the person's willingness to review every
  proposal — a cost that grows with use.
- Tiny ecosystem; adapters for only a few agent surfaces.

### Visible vs Hidden Metrics

- **Visible:** "no lock-in", "no server/vector DB", granular sharing, works with several agents,
  open MIT spec with conformance kit. All self-reported; adoption metrics are minimal and no
  independent evaluation exists.
- **Hidden:** spec churn (adopters track a moving provisional standard); vocabulary/learning curve;
  curation burden — structure-as-index only works if someone keeps the tree tidy; per-capture review
  fatigue; git-as-database limits (merge conflicts on shared notes, no concurrent multi-writer story
  locally); hosted features create the real lock-in the local story disclaims.
- **Weighing:** adopting the *protocol or product* is a poor trade — churn and vocabulary cost
  outweigh the gains for a system that already has its own memory/KB stack. The *patterns* are cheap
  and portable: summary-first loading of instruction files, head/tail cache-aware rendering,
  reference-vs-authority separation for foreign instructions, exact-path optimistic-concurrency
  commits with honest `partial` results, and propose-then-confirm capture. Those carry the visible
  wins with almost none of the hidden costs.

---

## AutoBot Comparison

Paths are relative to `autobot-backend/` unless prefixed otherwise.

### What We Can Adopt

| # | Pattern | AutoBot file(s) it applies to | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| A | Propose-then-confirm memory capture | `chat_workflow/stop_hook.py:28`, `tools/tool_registry.py:485-496`, `services/approval_gate_service.py`, `models/approval.py:37` | Capture is implicit: `on_turn_complete` fire-and-forget enqueues `memory.write_verbatim` + `memory.extract_facts` every turn (called from `chat_workflow/manager.py:3598`). `store_fact` writes to the KB directly, tagged `ingest_route: agent_tool`, no approval call in the method (dispatch-layer gating not checked). `ApprovalType` has 10 types, none for memory/facts. Only review queue is admin-only KB source verification (`api/knowledge_verification.py`, `KnowledgeVerificationQueue.vue`), fed by connectors. Users can view/delete memories (`autobot-frontend/src/components/settings/MemoryPrivacyPanel.vue`); the amend endpoint `PUT /memory/privacy/{store}/{memory_id}` (`api/memory_privacy.py:248`) has no UI caller. | Agent-initiated durable facts stop landing unreviewed; aligns with owner rule #17038 | Review fatigue grows with use | adopt-with-conditions: only agent-initiated durable facts (`store_fact`, extracted facts), batched per session via `approval_gate_service.py`; verbatim turn logs stay automatic | moderate |
| B | Skills loaded name+description, body on selection | `skills/registry.py:469`, `skills/prepared_facts.py:91`, `skills/builtin/skill_router.py:183`, `llm_handler.py:624`, `context_window_manager.py:279,423` | `_parse_skill_md` parses only name/description frontmatter into a manifest; `SkillRoutingIndex` is used only at plan time (`skill_router.py:183` from `orchestration/workflow_planning.py:152`). Chat path (`chat_workflow/`, `agent_loop/`) references no skills; system prompt is one static file (`get_prompt("chat.system_prompt_simple")`). Nothing reads a SKILL.md body into a prompt. Token budget exists: `allocate_sections` (:279), `get_prompt_budget` (:423). | Skills become usable from chat without paying their full body every turn | Another prompt section to budget and cache-order; must sit in the stable head per #16836 | adopt | moderate |
| C | Head/tail placement as typed per-item attribute; byte-identical render | `llm_shared/providers/anthropic.py:264`, `llm_handler.py:921,928`, `context_window_manager.py:74`, `essential_story.py` | The hosted-provider adapter marks the whole system block `cache_control: ephemeral`; self-hosted inference prefix caching is a setting. `llm_handler.py:921` prepends per-turn `tiered_ctx` (built from the user message) ahead of the static prompt; `:928` prepends essential story (cached by fact fingerprint, mostly stable). Determinism pieces exist: name tie-break (`context_window_manager.py:74`), order-sensitive sha256 fingerprint (`essential_story.py`). Tracked: #17278, #16836, #16767, #17277. | Makes the cache-friendly layout normative instead of incidental | None beyond what #16836 already carries | adopt as design input to #16836 — no new issue | trivial (doc input) |
| D | Reference vs authority for foreign instructions | `security/content_firewall.py`, `knowledge/query_sanitizer.py:383`, `tools/parallel/executor.py:478`, `chat_workflow/delegation.py` | `wrap_untrusted_web_content` (closing-tag neutralization) and `content_firewall._delimit` with `ContentSource` MCP/WEB/RAG/FILE/STDOUT cover web, MCP, RAG, and every parallel-executor tool output (as STDOUT). `ContentSource.FILE` has no non-test caller. `delegation.py` has no firewall/wrap reference — delegated subagent output is not delimited. Non-parallel `read_file` path not traced. Umbrella #16777 (#16770, #16771, #16776). | Closes the two undelimited inputs (delegated output, file reads) | Marginal latency per delegated turn | adopt — as a child of #16777 | moderate |
| E | Atomic write + expected-revision precondition + honest `partial` | `api/filesystem_mcp.py:1011`, `api/git_mcp.py`, `autobot_shared/coordination/shared_runtime_bag.py:19`, `llc/models/work_item.py:128` | `write_file_mcp` is admin-only, validated path + per-file asyncio lock, then plain overwrite (no temp+replace, no expected hash). No runtime git-commit path exists (`git_mcp.py` read-only by design). Optimistic concurrency exists elsewhere: Redis WATCH/MULTI CAS (`shared_runtime_bag.py:19`), version counter (`work_item.py:128`). | Lost-update and torn-write protection on the one runtime file writer | Extra round-trip to hash before write | adopt-with-conditions for `write_file_mcp` only (atomic replace + optional expected sha256); git-commit half rejected-by-hidden-metrics (nothing to protect) | trivial-moderate |
| F | Provenance: cross-repo Change-Id / commit trailers | `services/audit_logger.py:95`, `chat_workflow/code_exec/broker.py:92` | `AuditEntry` carries session_id/user_id; `_emit_audit` emits run_id/tool/params_hash/ok with no session/conversation id. LLC has an immutable activity trail and replay log. No runtime commits, hence no trailers or change IDs. | Code-exec audit events become joinable to a conversation | None | Change-Id: rejected-by-hidden-metrics (no runtime git writes; dev process forbids commit trailers). Smaller delta — session/conversation id on the code-exec audit event — adopt | trivial |
| G | Progressive disclosure summary→outline→section→full as agent tools | `services/knowledge/doc_indexer.py:252,290`, `knowledge/summary_search.py:59,99`, `api/knowledge_graph_routes.py:247`, `markdown_reference_system.py:124` | `doc_indexer` chunks by H2/H3 into ChromaDB; `_parse_frontmatter` keeps body/tags/aliases, no summary field. `summary_search` has `get_document_overview` and `drill_down`, exposed only via REST; `markdown_reference_system` keeps a SQLite sections table, REST-only. No agent tool exposes outline/section reads. | Agent stops at the first sufficient rung instead of pulling full chunks | One more tool definition in the agent tool budget | adopt (wiring existing code, not new); README-as-folder-summary rejected-by-hidden-metrics (curation burden; KB is not folder-shaped) | moderate |
| H | The protocol/format itself; git-as-memory-store | — | AutoBot has Redis/Chroma/SQLite store authority via `autobot_shared/store_authority`. | — | Provisional churn, bespoke vocabulary (Phase 1 weighing) | rejected | — |

### What We Already Do Better

| Area | AutoBot | Reference work |
|---|---|---|
| Untrusted content | A firewall with quarantine verdicts and `ContentSource` delimiting across web, MCP, RAG and tool stdout | A structural rule only (`contractRole: reference`), no firewall |
| Knowledge retrieval | Semantic retrieval (ChromaDB) plus hierarchical summaries (`knowledge/summary_search.py`) at scale | Curated folder structure is the only index |
| Memory control for users | View/delete per store (`MemoryPrivacyPanel.vue`), backend amend endpoint, forget-everywhere flow | Edit-the-markdown-and-commit |
| Store authority | One durable store per concept, declared in `autobot_shared/store_authority` | git as the only store, single-writer locally |
| Concurrency | Redis CAS and version counters where multi-writer state exists | Per-path blob revisions on a single-user git tree |

### Gaps & Opportunities

Prioritized, highest first.

| Pri | Gap | Status |
|---|---|---|
| 1 | Per-turn `memory.extract_facts` task calls a nonexistent `extract_facts_from_messages` | tracked: #18075 (open) |
| 2 | Agent-initiated durable facts (`store_fact`, extracted facts) bypass any approval — add a proposed-memory path via `approval_gate_service.py` | NEW candidate (A); related: #18138 fact consolidation via approval gate |
| 3 | Delegated subagent output is not firewall-delimited; `ContentSource.FILE` unused by file reads | NEW candidate (D), child of #16777 |
| 4 | `write_file_mcp` plain overwrite, no atomic replace or expected hash | NEW candidate (E) |
| 5 | Skills invisible to the chat path; no name+description listing in the system prompt | NEW candidate (B) |
| 6 | `get_document_overview` / `drill_down` REST-only, no agent tool | NEW candidate (G) |
| 7 | Memory amend endpoint `PUT /memory/privacy/{store}/{memory_id}` has no UI caller | NEW candidate (A, frontend) |
| 8 | Code-exec audit event lacks session/conversation id | NEW candidate (F) |
| 9 | forget-everywhere skips KB facts | tracked: #18074 |
| 10 | Head/tail placement attribute and byte-identical render requirement | tracked: #16836 (design input only) |

### Specific Code/Files Affected

| Candidate | Files |
|---|---|
| A | `chat_workflow/stop_hook.py`, `tools/tool_registry.py`, `services/approval_gate_service.py`, `models/approval.py`, `api/memory_privacy.py`, `autobot-frontend/src/components/settings/MemoryPrivacyPanel.vue` |
| B | `skills/registry.py`, `skills/prepared_facts.py`, `llm_handler.py`, `context_window_manager.py` |
| C | `llm_handler.py`, `llm_shared/providers/anthropic.py` (via #16836) |
| D | `chat_workflow/delegation.py`, `security/content_firewall.py`, file-read tool path (untraced) |
| E | `api/filesystem_mcp.py` |
| F | `chat_workflow/code_exec/broker.py`, `services/audit_logger.py` |
| G | `knowledge/summary_search.py`, `tools/tool_registry.py`, `markdown_reference_system.py` |

**Already tracked — no new filing:** #18075 (extract task method missing), #18138 (fact consolidation via approval gate), #18074 (forget-everywhere KB facts), #17278 (per-turn prepend), #16836 (layering contract — receives C as design input), #16767 (layered role-holder prompts), #17277 (prompt drift detection), #16777 umbrella with #16770/#16771/#16776 (document→action taint).
