# Research: hosted knowledge-base chat agent platform

## Source Analysis: a commercial no-code SaaS for knowledge-grounded support/search agents

### What It Is
A vendor's hosted, mature (SOC 2 Type II) platform that turns an organisation's content into chat
and voice agents for customer support, pre-sales lead capture and internal knowledge search, and is
moving from "answer questions" to "take actions" in business tools. Closed source; everything below
comes from marketing and developer-overview pages and is self-reported.

### Architecture & Key Patterns
- Multi-tenant SaaS: team → bot → sources; hosted widget, public chat/search/admin REST APIs.
- "Agentic RAG": clean → chunk → retrieve candidates → rerank → generate; answers return a
  `sources` array (title + url).
- ~30-38 connector types: site crawl, sitemap, RSS, URL lists, files (PDF/Office/MD/CSV), A/V
  transcription, video transcripts, manual Q&A pairs, bulk CSV, wikis/KBs, cloud drives, help-desk
  **ticket history**, code hosts, team chat; many marked beta.
- Scheduled source re-sync (daily/weekly/monthly) plus manual refresh.
- Actions layer: "Skills" = an instruction markdown file + a TypeScript script of callable
  functions; remote MCP servers added by URL with per-tool enablement; webhooks, UI buttons,
  booking, billing. An in-product coding agent ("Skill Builder") writes/tests skills.
- Content unit is a "page" ≈ 5,000 cleaned chars; usage metered in credits with per-model
  multipliers (1x → 50x).

### Notable Implementation Details
- **Browser-side PII redaction**: a small local model in the visitor's browser redacts detected PII
  before the message leaves the device (top tiers only).
- **Ticket history as a knowledge source**: resolved support tickets ingested to answer new ones.
- **Answer in any language from English-only sources** (cross-lingual retrieval + generation).
- **Chat API exposes rating and escalation** as first-class endpoints alongside chat/streaming.
- **Tool calls recorded in conversation logs** for audit and tuning.
- **Least-privilege MCP guidance**: enable the smallest useful subset of a server's read/write tools.
- Analytics tiers: usage → topics, sentiment, resolution rate, satisfaction, AI-driven analysis.
- Deep-research mode combining KB + live web search + code interpreter, with citations.

### Strengths
- Breadth of connectors with scheduled freshness — the hard, unglamorous part of RAG.
- Clean progressive skill model (instructions load only when relevant; code is separate).
- Closed feedback loop: logs → ratings → Q&A-pair corrections → re-answer.
- Privacy-forward client-side redaction is a genuinely uncommon pattern.

### Weaknesses / Limitations
- Opaque retrieval: no embedding model, chunk size, vector store or reranker disclosed.
- No documented confirmation/approval step before an action runs — "actions only do what you
  design them to" is the whole safety story on the page.
- Hard stop when credits run out (bot goes silent).
- Inconsistent self-reported numbers (28+/37+/38+ sources); testimonial quality varies (~60% "really
  good" vs ~80% resolution claims).
- Many connectors beta / coming soon; deep analytics and branding removal tier-gated.
- Developer overview page (and the general docs index, HTTP 500 at fetch time) gives little detail
  on streaming format, rating/escalation fields or auth scopes.

### Visible vs Hidden Metrics
- **Visible (all self-reported):** source-type count, 100+ languages, SOC 2/GDPR/HIPAA badges,
  "10x more leads", ~80% resolution testimonial, 7,000+ apps via automation platforms.
- **Hidden:** each connector is a permanent maintenance liability (third-party API drift, auth
  renewal, rate limits); scheduled re-sync costs re-embedding compute and can silently go stale
  when a connector breaks; actions without a confirmation gate widen blast radius; credit
  multipliers make cost unpredictable; client-side PII model adds bundle weight and recall gaps
  (redaction misses are silent).
- **Weighing:** for a self-hosted platform the connector breadth is the most expensive thing to
  copy and the least differentiating; the cheap, high-leverage ideas are the patterns (ticket
  history as source, rating/escalation loop, per-tool MCP enablement, client-side redaction,
  scheduled freshness with staleness visibility).

## AutoBot Comparison: the reference work → AutoBot (audited against origin/main, 2026-10-27)

### What We Can Adopt
| # | Pattern | Audit (what was checked) | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| A1 | PII/safety scan on the embeddable widget path | `api/chat_embed.py:161,226` sends raw message to `llm_service.chat`; no `scan_chat_message` (present at 7 sites in `api/chat.py`); REDACTION_BOUNDARY.md names that module as the chat entry point | closes an unauthenticated, origin-`*` path that bypasses the redaction boundary | none: reuse of the existing module | **adopt (security bug, not a feature)** | trivial |
| A2 | Per-message answer rating → feedback loop | ABSENT: chat actions are edit/copy/delete only (`ChatMessages.vue:95-125`); existing `/rag-feedback` is per-KB-card, feeds `retrieval_learner.py:225` | real satisfaction signal for `analytics_conversation.py` (now heuristic, :597-606) and retrieval learning | storage + UI + abuse of ratings; only valuable if consumed | adopt-with-conditions: must feed the existing retrieval learner and analytics, no new store | moderate |
| A3 | Per-tool enable/disable on external MCP servers | `schemas_mcp_external_servers.py:27-60` has server-level `enabled`/`allowed_roles` only; grep `enabled_tools\|allowed_tools\|tool_allowlist` → 0; bridge exposes every discovered tool (`mcp_external_bridge.py:100`) | least privilege: write tools off by default | schema migration; tool list drift when a server adds tools (default-deny new tools) | **adopt** | moderate |
| A4 | Curated Q&A / correction entries that override retrieval | ABSENT: grep `qa_pair\|canned_answer\|answer_override\|verified_answer` → 0; closest is `/add_text`, `/facts` | deterministic fix for a known wrong answer | conflicts with `contradiction_detector.py`; correction rot | adopt-with-conditions: as a high-provenance KB fact class, ranked by existing provenance scoring in `reranking.py:278`, not a separate path | moderate |
| A5 | Overdue/failed-sync alerting for KB connectors | status + error shown (`ConnectorStatusCard.vue:91-102`); grep `overdue\|next_sync\|stale` in connector UI → 0; no notify in `scheduler.py` | silent connector rot becomes visible | small; reuse existing notification channel | **adopt** | trivial-moderate |
| A6 | Cross-lingual retrieval | answer language forced via `prompt_manager.py:1429-1448`; embeddings default `nomic-embed-text` (English-centric); no query translation | Latvian/other queries over English KB retrieve well | multilingual embedding = full re-index + model pin (MODEL_REVISION_PINNING) | adopt-with-conditions: measure recall on a Latvian query set first | significant |
| A7 | Skill instructions loaded into chat only when relevant | `skills/manifest_parser.py:44` parses SKILL.md; `DeclarativeSkill` has no execution path (`base_skill.py:206`); grep in `chat_workflow` → 0 | skills become usable from chat | prompt budget, relevance-selection quality | adopt-with-conditions: wire the existing registry (debris = unfinished work), no new skill format | moderate |
| A8 | User-initiated escalation from chat | agent-side `ask_human()` (`agent_loop/loop.py:1079`), takeover API (`advanced_control.py:157-283`); no user→human path | — | AutoBot is not a support desk; a ticket system is scope creep | **rejected-by-hidden-metrics** (positioning) | — |

### What We Already Do Better
- **Action safety:** approval gates with HMAC-bound tool-call fingerprints (`chat_workflow/approval_binding.py`, `graph.py:143`), per-tool permission gate (`tool_permission_gate.py:62`), approve/deny UI (`ApprovalRequestCard.vue`). The reference work documents no confirmation step at all.
- **Retrieval transparency:** cross-encoder rerank + MMR + recency/provenance/staleness blend (`reranking.py:375`), BM25+vector RRF hybrid (`hybrid_search.py:70`), stale-chunk filtering (`stale_filter.py:97`), ungrounded-answer badge (`MessageItem.vue:124`). The reference work discloses none of its retrieval internals.
- **Self-hosted, no credit cliff:** local models; no "bot stops when credits run out" failure mode.
- **Scheduled sync** already exists (`connectors/scheduler.py:91`, Redis leader lease, incremental sync).
- **Embeddable widget** already exists (`embed/AutobotWidget.ts`, SRI build).

### Gaps & Opportunities (by impact)
1. A1 widget safety-scan bypass (security).
2. A3 per-tool MCP allowlist.
3. A2 answer ratings feeding the existing learner + analytics.
4. A5 sync-failure/overdue alerting.
5. A7 wire SKILL.md instructions into chat.
6. A4 curated corrections as a provenance class.
7. A6 cross-lingual retrieval (measure first).
- Not pursued: connector breadth (ticket history, cloud drives beyond current set) — high maintenance, low differentiation; client-side browser PII model — server-side boundary already exists, a browser model adds bundle weight and silent misses.
- Side observations (verify before filing): `knowledge/search.py:237` defaults `enable_reranking=False`; sitemap mapper not used by the crawler connector; `analytics_conversation.py:673` globs `data/chat_history/*.json` — may not match current chat storage.

### Specific Code/Files Affected
- `autobot-backend/api/chat_embed.py` — call `scan_chat_message` before both `llm_service.chat` sites.
- `autobot-backend/api/schemas_mcp_external_servers.py`, `services/mcp_external_bridge.py`, `views/AdminMcpServersView.vue` — per-tool allowlist, default-deny new tools.
- `autobot-frontend/src/components/chat/MessageItem.vue` + a chat rating route → `retrieval_learner.py` stream and `analytics_conversation.py`.
- `knowledge/connectors/scheduler.py`, `ConnectorStatusCard.vue` — overdue/failed alert.
- `chat_workflow/*` + `skills/registry.py` — relevant-skill instruction loading.

## Linked issues

- #19794 Umbrella: knowledge-chat agent gaps — widget safety, MCP tool scoping, KB freshness, answer feedback
- #19786 security(chat): embeddable-widget endpoint skips scan_chat_message — raw visitor text reaches the LLM unredacted
- #19787 feat(mcp): per-tool allowlist for external MCP servers, default-deny newly discovered tools
- #19788 feat(kb): KB connector sync — overdue state and failure/overdue notifications
- #19789 feat(chat): per-answer rating that feeds the retrieval learner and conversation analytics
- #19790 feat(skills): inject relevant SKILL.md instructions into chat within a token budget
- #19791 feat(kb): curated Q&A entries ranked by provenance weight
- #19792 research(kb): measure cross-lingual retrieval (Latvian query → English KB) before any embedding change
- #19793 investigate(kb): reranking default off, sitemap unwired in crawler, analytics chat-history path
