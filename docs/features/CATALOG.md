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

A single map of what AutoBot can do — including capabilities that were previously
documented only in archived plans, design specs, and implementation reports and were
not reachable from the main navigation. Use it as the discovery surface for the
platform's real feature set.

> **About the Status column.** Status is *derived from each capability's own
> documentation* and has **not** been independently re-verified against the running
> code. Treat it as a pointer, not a guarantee:
> - **Shipped** — the source doc describes it as implemented/complete.
> - **Partial** — built but incomplete, or backend-only/awaiting wire-in.
> - **Planned** — specified in a PRD/plan, implementation not confirmed started.
> - **Design** — design spec only.
>
> Before making any headline/marketing claim from this table, verify the specific
> capability against the codebase. See the [Platform Model](../architecture/PLATFORM_MODEL.md)
> for how these capabilities fit together.

---

## Conversation & Voice

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Voice conversation mode | Design | [archives/plans/2026-02-20-voice-conversation-mode-design](../archives/plans/2026-02-20-voice-conversation-mode-design.md) | Walkie-talkie, hands-free, and duplex voice interaction modes |
| Streaming TTS (per-sentence) | Design | [archives/plans](../archives/_index.md) | Real-time per-sentence text-to-speech (1.5–3s latency) instead of waiting for the full reply |
| Chat knowledge management | Shipped | [implementation/CHAT_KNOWLEDGE_MANAGEMENT](../implementation/CHAT_KNOWLEDGE_MANAGEMENT.md) | Chat-scoped knowledge context, file associations, conversation→KB compilation, topic detection |

## Knowledge, RAG & Memory

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Graph-RAG hybrid search | Shipped | [planning/issue-55-complete-summary](../planning/issue-55-complete-summary.md) | Weighted vector + knowledge-graph retrieval with entity extraction at query time |
| Graph entity extractor | Shipped | [planning/issue-55-complete-summary](../planning/issue-55-complete-summary.md) | Extracts facts/entities from conversations and infers relationships (REST API) |
| Memory graph semantic search | Shipped | [design/MEMORY_GRAPH_SEMANTIC_SEARCH](../design/MEMORY_GRAPH_SEMANTIC_SEARCH.md) | Hybrid full-text + vector search over the memory graph (<100ms target) |
| Enhanced memory manager | Shipped | [implementation/PHASE_7_MEMORY_ENHANCEMENT](../implementation/PHASE_7_MEMORY_ENHANCEMENT.md) | Task execution history, embedding cache, subtask relationships, task lifecycle |
| RAG optimization suite | Planned | [planning/RAG_Optimization_Implementation_Plan](../planning/RAG_Optimization_Implementation_Plan.md) | Semantic chunking, atomic facts, entity resolution, temporal invalidation, temporal KG |
| Neural Mesh RAG | Design | [archives/plans/2026-03-22-neural-mesh-rag-design](../archives/plans/2026-03-22-neural-mesh-rag-design.md) | Self-evolving RAG architecture with multi-hop reasoning |
| Individual document vectorization | Partial | [design/individual-document-vectorization-ux-spec](../design/individual-document-vectorization-ux-spec.md) | Per-document vectorization triggers and status indicators in the file browser |
| Knowledge-enhanced chat | Partial | [features/knowledge_chat_integration](knowledge_chat_integration.md) | RAG context augmentation with source citation in chat |
| MCP knowledge-base tools | Shipped | [features/mcp-knowledge-base-integration](mcp-knowledge-base-integration.md) | Direct LLM access to the KB via MCP (search, add, similarity, QA chain) |

## Code Intelligence & Analytics

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Advanced code intelligence | Planned | [implementation/AutoBot_Advanced_Code_Intelligence](../implementation/AutoBot_Advanced_Code_Intelligence.md) | ~30 analyses: semantic code search, git-evolution mining, CFG/data-flow, bug prediction, auto review |
| Code intelligence dashboard | Shipped | [archives/plans/2026-02-04-code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | Real-time code-health dashboard with bug-prediction trends |
| Code pattern detection | Planned | [implementation/Graph_code_patern_detection](../implementation/Graph_code_patern_detection.md) | RAG-based duplicate/anti-pattern detection, dead-code and complexity hotspots |
| Error monitoring | Shipped | [archives/plans/2026-02-04-code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | Live error monitoring with auto-refresh |
| Causal inference engine | Shipped | [changelog](../changelog/_index.md) | Root-cause and confounder analysis |
| Advanced visualizations | Shipped | [features/ADVANCED_VISUALIZATIONS](ADVANCED_VISUALIZATIONS.md) | Resource heatmaps, animated workflow graphs, agent-activity dashboards |

## Vision, Browser & Desktop

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Interactive browser control | Design | [archives/plans/2026-03-06-interactive-browser-control-design](../archives/plans/2026-03-06-interactive-browser-control-design.md) | Screenshot-guided browser automation with visual feedback loops |
| Desktop streaming & takeover | Shipped | [implementation/PHASE_8_ENHANCED_INTERFACE](../implementation/PHASE_8_ENHANCED_INTERFACE.md) | NoVNC desktop streaming with human takeover/approval workflow |
| Vision-automation integration | Design | [archives/plans](../archives/_index.md) | Vision-guided UI testing and automation |

## Automation, Safety & Human-in-the-loop

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Session takeover & control | Shipped | [implementation/COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION](../implementation/COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION.md) | Pause/resume, step confirmation, emergency kill, risk assessment |
| Terminal safety | Shipped | [implementation/TERMINAL_SAFETY_IMPLEMENTATION](../implementation/TERMINAL_SAFETY_IMPLEMENTATION.md) | Command risk assessment, dangerous-command confirmation, Ctrl+C interrupt |
| Skills system | Shipped | [archives/plans/2026-02-18-skills-system](../archives/plans/2026-02-18-skills-system.md) | Dynamic skill discovery and routing (e.g. two-phase Research skill) |

## Fleet, SLM & Infrastructure Ops

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Service Lifecycle Manager (SLM) | Shipped | [guides/slm-docker-ansible-deployment](../guides/slm-docker-ansible-deployment.md) | Deploy, operate, and scale the AI infrastructure fleet (see [Platform Model](../architecture/PLATFORM_MODEL.md)) |
| SLM bash execution | Shipped | [guides/slm-bash-execution](../guides/slm-bash-execution.md) | Run bash across target groups of fleet nodes |
| NPU worker pool | Design | [archives/plans/2026-02-05-npu-worker-pool-design](../archives/plans/2026-02-05-npu-worker-pool-design.md) | Load-balanced NPU inference pool with circuit breaker + health monitoring |
| Windows native NPU deployment | Planned | [research/INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS](../research/INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS.md) | Intel NPU acceleration natively on a Windows host via OpenVINO |
| Release system (git-cliff) | Shipped | [archives/plans/2026-03-01-release-system-design](../archives/plans/2026-03-01-release-system-design.md) | Automated release notes + in-app system update indicators |
| Service discovery & message bus | Design | [archives/plans/2026-02-02-service-discovery-design](../archives/plans/2026-02-02-service-discovery-design.md) | Dynamic service discovery, message bus + state machine, mTLS service auth |
| Configuration management | Planned | [planning/CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN](../planning/CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN.md) | Env-var priority enforcement, startup validation, settings sync, hot reload |

## Security & Governance

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Service auth enforcement | Shipped | [planning/WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN](../planning/WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN.md) | JWT service-to-service authentication across the fleet |
| Secrets management | Partial | [implementation/secrets_management_system](../implementation/secrets_management_system.md) | AES-256 encrypted, dual-scope (general + chat) secrets with audit logging |

## Platform Extensibility

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| Plugin SDK | Partial | [superpowers/plans/2026-05-05-plugin-sdk-required-env](../superpowers/plans/2026-05-05-plugin-sdk-required-env.md) | Build modules/adapters against the platform via the plugin SDK |
| MCP agent workflows | Shipped | [examples/mcp_agent_workflows](../examples/mcp_agent_workflows/README.md) | Example MCP agent workflows (code analysis, research, VNC monitoring) |
| Language switcher (i18n) | Partial | [superpowers/plans/2026-04-07-language-switcher](../superpowers/plans/2026-04-07-language-switcher.md) | Multi-language UI with dynamic switching |

## Emerging Modules & Surfaces

| Capability | Status | Source | What it does |
|------------|--------|--------|--------------|
| AutoBot LLC module | Planned | [llc/_index](../llc/_index.md) | Autonomous agent-company module — see the [module overview](../llc/_index.md) |
| Live Canvas | Partial | [superpowers/plans/2026-05-16-live-canvas-phase1](../superpowers/plans/2026-05-16-live-canvas-phase1.md) | Collaborative agent/user canvas with streaming cells and multi-format export |
| Transcriber module | Partial | [superpowers/plans/2026-05-30-transcriber-plan-1-foundation](../superpowers/plans/2026-05-30-transcriber-plan-1-foundation.md) | General-purpose audio transcription module with projects/recordings |
| AutoResearch | Partial | [superpowers/plans/2026-04-01-autoresearch-m3](../superpowers/plans/2026-04-01-autoresearch-m3.md) | Self-improving research system with a dashboard |

---

## How this catalog was built

This catalog consolidates a sweep of the archived/planning/design/implementation
documentation zones (`archives/`, `planning/`, `discovery/`, `research/`, `design/`,
`designs/`, `implementation/`, `superpowers/`, `examples/`, `changelog/`, `releases/`)
for capabilities that were not reachable from [INDEX.md](../INDEX.md). Pure refactors,
CI plumbing, and internal test infrastructure were excluded.

If a capability here is confirmed shipped, promote it into the relevant section MOC
(e.g. [Features](_index.md)) and into [INDEX.md](../INDEX.md). If it is stale or
abandoned, move its source doc to [archives/](../archives/_index.md).

## Related

- [Features Index](_index.md)
- [The AutoBot Platform Model](../architecture/PLATFORM_MODEL.md)
- [AutoBot LLC](../llc/_index.md)
- [Glossary](../GLOSSARY.md)
