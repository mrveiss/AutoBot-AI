---
tags:
  - features
  - index
  - catalog
aliases:
  - Capability Catalog
  - Feature Catalog
  - What AutoBot Can Do
  - Buried Features
status: current
---

# AutoBot Capability Catalog

**This is the single registry for AutoBot features.** Feature documentation lives in one
place — `docs/features/` — and this catalog is its index: every capability maps to a
**design doc** and a **tracking issue**, with verification owned by the issue. It includes
capabilities that were previously documented only in archived plans, design specs, and
implementation reports and were not reachable from the main navigation.

> **Tracking & verification.** Every capability below is tracked under umbrella issue
> [#9872][u]. Until per-feature verification issues are filed under it, the **Issue**
> column points at the umbrella. **Verification tasks live in the issues, not here** —
> see the verification template in [#9872][u].

> **About the Status column.** Status is *derived from each capability's own
> documentation* and has **not** been independently re-verified against the running
> code. Treat it as a pointer, not a guarantee:
> - **Shipped** — the source doc describes it as implemented/complete.
> - **Partial** — built but incomplete, or backend-only/awaiting wire-in.
> - **Planned** — specified in a PRD/plan, implementation not confirmed started.
> - **Design** — design spec only.
>
> Before making any headline/marketing claim from this table, verify the specific
> capability against the codebase (that is what [#9872][u] is for). See the
> [Platform Model](../architecture/PLATFORM_MODEL.md) for how these capabilities fit together.

---

## Modules

Some capabilities are packaged as **installable modules** built on the
[platform core](../architecture/PLATFORM_MODEL.md), not as part of the core itself:

| Module | Status | Design doc | Issue | What it adds |
|--------|--------|------------|-------|--------------|
| **AutoBot LLC** | Planned | [llc/_index](../llc/_index.md), [PRD](../planning/PRD_AutoBot_LLC_Module.md) | [#9872][u] | Autonomous agent-company: agents, goals, backlog, heartbeat scheduling, board governance |
| **Codebase Analytics** | Shipped | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9872][u] | Code structure analysis, risk detection, dependency insights — on your own hardware |
| **Transcriber** | Partial | [transcriber-plan-1-foundation](../superpowers/plans/2026-05-30-transcriber-plan-1-foundation.md) | [#9872][u] | Audio transcription module: projects, recordings, local transcription, export |

The themed tables below break down the capabilities inside the core and these modules.

---

## Conversation & Voice

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Voice conversation mode | Design | [voice-conversation-mode-design](../archives/plans/2026-02-20-voice-conversation-mode-design.md) | [#9872][u] | Walkie-talkie, hands-free, and duplex voice interaction modes |
| Streaming TTS (per-sentence) | Design | [archives/plans](../archives/_index.md) | [#9872][u] | Real-time per-sentence text-to-speech (1.5–3s latency) instead of waiting for the full reply |
| Chat knowledge management | Shipped | [CHAT_KNOWLEDGE_MANAGEMENT](../implementation/CHAT_KNOWLEDGE_MANAGEMENT.md) | [#9872][u] | Chat-scoped knowledge context, file associations, conversation→KB compilation, topic detection |

## Knowledge, RAG & Memory

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Graph-RAG hybrid search | Shipped | [issue-55-complete-summary](../planning/issue-55-complete-summary.md) | [#9872][u] | Weighted vector + knowledge-graph retrieval with entity extraction at query time |
| Graph entity extractor | Shipped | [issue-55-complete-summary](../planning/issue-55-complete-summary.md) | [#9872][u] | Extracts facts/entities from conversations and infers relationships (REST API) |
| Memory graph semantic search | Shipped | [MEMORY_GRAPH_SEMANTIC_SEARCH](../design/MEMORY_GRAPH_SEMANTIC_SEARCH.md) | [#9872][u] | Hybrid full-text + vector search over the memory graph (<100ms target) |
| Enhanced memory manager | Shipped | [PHASE_7_MEMORY_ENHANCEMENT](../implementation/PHASE_7_MEMORY_ENHANCEMENT.md) | [#9872][u] | Task execution history, embedding cache, subtask relationships, task lifecycle |
| RAG optimization suite | Planned | [RAG_Optimization_Implementation_Plan](../planning/RAG_Optimization_Implementation_Plan.md) | [#9872][u] | Semantic chunking, atomic facts, entity resolution, temporal invalidation, temporal KG |
| Neural Mesh RAG | Design | [neural-mesh-rag-design](../archives/plans/2026-03-22-neural-mesh-rag-design.md) | [#9872][u] | Self-evolving RAG architecture with multi-hop reasoning |
| Individual document vectorization | Partial | [individual-document-vectorization-ux-spec](../design/individual-document-vectorization-ux-spec.md) | [#9872][u] | Per-document vectorization triggers and status indicators in the file browser |
| Knowledge-enhanced chat | Partial | [knowledge_chat_integration](knowledge_chat_integration.md) | [#9872][u] | RAG context augmentation with source citation in chat |
| MCP knowledge-base tools | Shipped | [mcp-knowledge-base-integration](mcp-knowledge-base-integration.md) | [#9872][u] | Direct LLM access to the KB via MCP (search, add, similarity, QA chain) |

## Code Intelligence & Analytics

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Advanced code intelligence | Planned | [AutoBot_Advanced_Code_Intelligence](../implementation/AutoBot_Advanced_Code_Intelligence.md) | [#9872][u] | ~30 analyses: semantic code search, git-evolution mining, CFG/data-flow, bug prediction, auto review |
| Code intelligence dashboard | Shipped | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9872][u] | Real-time code-health dashboard with bug-prediction trends |
| Code pattern detection | Planned | [Graph_code_patern_detection](../implementation/Graph_code_patern_detection.md) | [#9872][u] | RAG-based duplicate/anti-pattern detection, dead-code and complexity hotspots |
| Error monitoring | Shipped | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9872][u] | Live error monitoring with auto-refresh |
| Causal inference engine | Shipped | [changelog](../changelog/_index.md) | [#9872][u] | Root-cause and confounder analysis |
| Advanced visualizations | Shipped | [ADVANCED_VISUALIZATIONS](ADVANCED_VISUALIZATIONS.md) | [#9872][u] | Resource heatmaps, animated workflow graphs, agent-activity dashboards |

## Vision, Browser & Desktop

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Interactive browser control | Design | [interactive-browser-control-design](../archives/plans/2026-03-06-interactive-browser-control-design.md) | [#9872][u] | Screenshot-guided browser automation with visual feedback loops |
| Desktop streaming & takeover | Shipped | [PHASE_8_ENHANCED_INTERFACE](../implementation/PHASE_8_ENHANCED_INTERFACE.md) | [#9872][u] | NoVNC desktop streaming with human takeover/approval workflow |
| Vision-automation integration | Design | [archives/plans](../archives/_index.md) | [#9872][u] | Vision-guided UI testing and automation |

## Automation, Safety & Human-in-the-loop

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Session takeover & control | Shipped | [COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION](../implementation/COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION.md) | [#9872][u] | Pause/resume, step confirmation, emergency kill, risk assessment |
| Terminal safety | Shipped | [TERMINAL_SAFETY_IMPLEMENTATION](../implementation/TERMINAL_SAFETY_IMPLEMENTATION.md) | [#9872][u] | Command risk assessment, dangerous-command confirmation, Ctrl+C interrupt |
| Skills system | Shipped | [skills-system](../archives/plans/2026-02-18-skills-system.md) | [#9872][u] | Dynamic skill discovery and routing (e.g. two-phase Research skill) |

## Fleet, SLM & Infrastructure Ops

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Service Lifecycle Manager (SLM) | Shipped | [slm-docker-ansible-deployment](../guides/slm-docker-ansible-deployment.md) | [#9872][u] | Deploy, operate, and scale the AI infrastructure fleet (see [Platform Model](../architecture/PLATFORM_MODEL.md)) |
| SLM bash execution | Shipped | [slm-bash-execution](../guides/slm-bash-execution.md) | [#9872][u] | Run bash across target groups of fleet nodes |
| NPU worker pool | Design | [npu-worker-pool-design](../archives/plans/2026-02-05-npu-worker-pool-design.md) | [#9872][u] | Load-balanced NPU inference pool with circuit breaker + health monitoring |
| Windows native NPU deployment | Planned | [INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS](../research/INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS.md) | [#9872][u] | Intel NPU acceleration natively on a Windows host via OpenVINO |
| Release system (git-cliff) | Shipped | [release-system-design](../archives/plans/2026-03-01-release-system-design.md) | [#9872][u] | Automated release notes + in-app system update indicators |
| Service discovery & message bus | Design | [service-discovery-design](../archives/plans/2026-02-02-service-discovery-design.md) | [#9872][u] | Dynamic service discovery, message bus + state machine, mTLS service auth |
| Configuration management | Planned | [CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN](../planning/CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN.md) | [#9872][u] | Env-var priority enforcement, startup validation, settings sync, hot reload |

## Security & Governance

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Service auth enforcement | Shipped | [WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN](../planning/WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN.md) | [#9872][u] | JWT service-to-service authentication across the fleet |
| Secrets management | Partial | [secrets_management_system](../implementation/secrets_management_system.md) | [#9872][u] | AES-256 encrypted, dual-scope (general + chat) secrets with audit logging |

## Platform Extensibility

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Plugin SDK | Partial | [plugin-sdk-required-env](../superpowers/plans/2026-05-05-plugin-sdk-required-env.md) | [#9872][u] | Build modules/adapters against the platform via the plugin SDK |
| MCP agent workflows | Shipped | [mcp_agent_workflows](../examples/mcp_agent_workflows/README.md) | [#9872][u] | Example MCP agent workflows (code analysis, research, VNC monitoring) |
| Language switcher (i18n) | Partial | [language-switcher](../superpowers/plans/2026-04-07-language-switcher.md) | [#9872][u] | Multi-language UI with dynamic switching |

## Emerging Surfaces

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Live Canvas | Partial | [live-canvas-phase1](../superpowers/plans/2026-05-16-live-canvas-phase1.md) | [#9872][u] | Collaborative agent/user canvas with streaming cells and multi-format export |
| AutoResearch | Partial | [autoresearch-m3](../superpowers/plans/2026-04-01-autoresearch-m3.md) | [#9872][u] | Self-improving research system with a dashboard |

---

## Single home for feature docs

`docs/features/` is the **single canonical home** for feature documentation, and this
catalog is its registry. Many capabilities above still have their design docs in other
zones (`implementation/`, `design/`, `archives/plans/`, `superpowers/plans/`,
`planning/`, `research/`). Consolidating those into the single home — with inbound links
rewritten to preserve the Obsidian graph and Jekyll — is tracked under [#9872][u].

## How this catalog was built

This catalog consolidates a sweep of the archived/planning/design/implementation
documentation zones (`archives/`, `planning/`, `discovery/`, `research/`, `design/`,
`designs/`, `implementation/`, `superpowers/`, `examples/`, `changelog/`, `releases/`)
for capabilities that were not reachable from [INDEX.md](../INDEX.md). Pure refactors,
CI plumbing, and internal test infrastructure were excluded.

Per-feature verification happens in issues filed under [#9872][u]. When a capability is
confirmed shipped, promote it into [INDEX.md](../INDEX.md); if it is stale or abandoned,
move its design doc to [archives/](../archives/_index.md) and update the row.

## Related

- [Features Index](_index.md)
- [The AutoBot Platform Model](../architecture/PLATFORM_MODEL.md)
- [AutoBot LLC](../llc/_index.md)
- [Glossary](../GLOSSARY.md)

[u]: https://github.com/mrveiss/AutoBot-AI/issues/9872
