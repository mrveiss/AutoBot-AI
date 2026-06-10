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
**design doc** and a **tracking issue**. It includes capabilities that were previously
documented only in archived plans, design specs, and implementation reports and were not
reachable from the main navigation.

> **Verified.** Statuses below were verified against the codebase on **2026-06-10**
> (evidence captured in the linked issues [#9874][i-voice]–[#9885][i-trans], under
> umbrella [#9872][u]). Most capabilities verified as **more complete** than first
> documented. Remaining gaps are tracked as discovery issues — see
> [Gaps found during verification](#gaps-found-during-verification).
>
> - **Shipped** — implemented and wired end-to-end (backend + frontend where applicable), with code evidence.
> - **Partial** — backend shipped but no frontend consumer, or a sub-capability still planned. Each has a wire-in issue.
> - **Planned** — specified, implementation not yet started.
> - **Design** — design spec only.
>
> See the [Platform Model](../architecture/PLATFORM_MODEL.md) for how these fit together.

---

## Modules

Some capabilities are packaged as **installable modules** built on the
[platform core](../architecture/PLATFORM_MODEL.md), not as part of the core itself:

| Module | Status | Design doc | Issue | What it adds |
|--------|--------|------------|-------|--------------|
| **AutoBot LLC** | Shipped | [llc/_index](../llc/_index.md), [PRD](../planning/PRD_AutoBot_LLC_Module.md) | [#9883][i-llc] | Autonomous agent-company: 27 LLC routers under `/api/llc`, heartbeat/adapters, full `views/llc/` UI (incremental follow-ups remain) |
| **Codebase Analytics** | Shipped | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9884][i-analytics] | Code structure analysis, risk detection, dependency insights — `/analytics/codebase` end-to-end |
| **Transcriber** | Shipped | [transcriber-plan-1-foundation](../superpowers/plans/2026-05-30-transcriber-plan-1-foundation.md) | [#9885][i-trans] | Audio transcription module: projects, recordings, local pipeline (diarization), export (srt/vtt/docx/pdf), UI |

The themed tables below break down the capabilities inside the core and these modules.

---

## Conversation & Voice

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Voice conversation mode | Shipped | [voice-conversation-mode-design](../archives/plans/2026-02-20-voice-conversation-mode-design.md) | [#9874][i-voice] | Walkie-talkie, hands-free, duplex, and realtime-WebRTC modes (`/voice` WS + `useVoiceConversation`) |
| Streaming TTS (per-sentence) | Shipped | [archives/plans](../archives/_index.md) | [#9874][i-voice] | Real-time pipelined per-sentence text-to-speech (`_tts_queue_worker`, `AUTOBOT_TTS_PIPELINE_DEPTH`) |
| Chat knowledge management | Shipped | [CHAT_KNOWLEDGE_MANAGEMENT](CHAT_KNOWLEDGE_MANAGEMENT.md) | [#9874][i-voice] | Chat-scoped knowledge, file associations, conversation→KB compilation (11 endpoints) |

## Knowledge, RAG & Memory

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Graph-RAG hybrid search | Shipped | [issue-55-complete-summary](../planning/issue-55-complete-summary.md) | [#9875][i-rag] | Weighted vector + knowledge-graph retrieval with entity extraction at query time (`/graph-rag/search`) |
| Graph entity extractor | Shipped | [issue-55-complete-summary](../planning/issue-55-complete-summary.md) | [#9875][i-rag] | Extracts facts/entities from conversations, infers relationships (`/entities/extract`) |
| Memory graph semantic search | Shipped | [MEMORY_GRAPH_SEMANTIC_SEARCH](MEMORY_GRAPH_SEMANTIC_SEARCH.md) | [#9875][i-rag] | Hybrid full-text + vector over the memory graph (service layer; consumed internally — no public REST) |
| Enhanced memory manager | Shipped | [PHASE_7_MEMORY_ENHANCEMENT](PHASE_7_MEMORY_ENHANCEMENT.md) | [#9875][i-rag] | Task execution history, embedding cache, subtask relationships, task lifecycle |
| RAG optimization suite | Shipped | [RAG_Optimization_Implementation_Plan](../planning/RAG_Optimization_Implementation_Plan.md) | [#9875][i-rag] | Semantic chunking, atomic facts, entity resolution, temporal invalidation + temporal KG (all four pillars present) |
| Neural Mesh RAG | Shipped | [neural-mesh-rag-design](../archives/plans/2026-03-22-neural-mesh-rag-design.md) | [#9875][i-rag] | Self-evolving RAG (`neural_mesh_retriever` + `mesh_brain/`: promoter, pruner, edge-learner; mesh tables) |
| Individual document vectorization | Shipped | [individual-document-vectorization-ux-spec](individual-document-vectorization-ux-spec.md) | [#9875][i-rag] | Per-document vectorization triggers + status badges in the file tree (both ends wired) |
| Knowledge-enhanced chat | Shipped | [knowledge_chat_integration](knowledge_chat_integration.md) | [#9875][i-rag] | RAG context augmentation with source citations in chat (`CitationsDisplay.vue`) |
| MCP knowledge-base tools | Shipped | [mcp-knowledge-base-integration](mcp-knowledge-base-integration.md) | [#9875][i-rag] | Direct LLM access to the KB via MCP (search, add, similarity, QA chain) |

## Code Intelligence & Analytics

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Advanced code intelligence | Partial | [AutoBot_Advanced_Code_Intelligence](AutoBot_Advanced_Code_Intelligence.md) | [#9876][i-code] | 31 endpoints: git-evolution, CFG/data-flow, bug prediction, auto review (shipped); semantic NL code search still planned |
| Code intelligence dashboard | Shipped | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9876][i-code] | Real-time code-health dashboard with bug-prediction trends (`useCodeIntelligence`) |
| Code pattern detection | Shipped | [Graph_code_patern_detection](Graph_code_patern_detection.md) | [#9876][i-code] | RAG-based duplicate/anti-pattern detection (ChromaDB + NPU embeddings), dead-code/complexity |
| Error monitoring | Partial | [code-intelligence-dashboard-design](../archives/plans/2026-02-04-code-intelligence-dashboard-design.md) | [#9876][i-code] | 12 backend endpoints shipped; **no frontend consumer** (wire-in [#9891](https://github.com/mrveiss/AutoBot-AI/issues/9891)) |
| Causal inference engine | Partial | [changelog](../changelog/_index.md) | [#9876][i-code] | Root-cause/confounder analysis shipped (`/diagnostics/analyze-failure`); **no UI consumer** (wire-in [#9892](https://github.com/mrveiss/AutoBot-AI/issues/9892)) |
| Advanced visualizations | Shipped | [ADVANCED_VISUALIZATIONS](ADVANCED_VISUALIZATIONS.md) | [#9876][i-code] | Resource heatmaps, workflow graphs, agent-activity dashboards (in `CustomDashboard.vue`) |

## Vision, Browser & Desktop

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Interactive browser control | Shipped | [interactive-browser-control-design](../archives/plans/2026-03-06-interactive-browser-control-design.md) | [#9877][i-vision] | Navigate/click/fill/screenshot automation + live stream (`/browser`, `BrowserAutomationView.vue`) |
| Desktop streaming & takeover | Shipped | [PHASE_8_ENHANCED_INTERFACE](PHASE_8_ENHANCED_INTERFACE.md) | [#9877][i-vision] | NoVNC desktop streaming with human takeover/approval (`/streaming/*`, `/takeover/*`) |
| Vision-automation integration | Partial | [archives/plans](../archives/_index.md) | [#9877][i-vision] | Vision `/analyze`,`/ocr`,`/automation-opportunities` shipped; **no frontend consumer** (wire-in [#9890](https://github.com/mrveiss/AutoBot-AI/issues/9890)) |

## Automation, Safety & Human-in-the-loop

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Session takeover & control | Shipped | [COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION](COMPLETE_SESSION_TAKEOVER_IMPLEMENTATION.md) | [#9878][i-auto] | Pause/resume, approval gate, risk triggers (`takeover_manager`, `/takeover/*`) |
| Terminal safety | Shipped | [TERMINAL_SAFETY_IMPLEMENTATION](TERMINAL_SAFETY_IMPLEMENTATION.md) | [#9878][i-auto] | Command risk assessment + dangerous-command confirmation gate (`command_patterns`, `security_risk_judge`) |
| Skills system | Shipped | [skills-system](../archives/plans/2026-02-18-skills-system.md) | [#9878][i-auto] | Skill discovery + 3-phase routing (`skill_router`, `/skills`) |

## Fleet, SLM & Infrastructure Ops

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Service Lifecycle Manager (SLM) | Shipped | [slm-docker-ansible-deployment](../guides/slm-docker-ansible-deployment.md) | [#9879][i-fleet] | Fleet deploy/operate/scale control plane (`autobot-slm-backend`, 40+ routers, ansible suite) |
| SLM bash execution | Shipped | [slm-bash-execution](../guides/slm-bash-execution.md) | [#9879][i-fleet] | Run bash across node groups (`/infrastructure/execute`) + per-node execution |
| NPU worker pool | Shipped | [npu-worker-pool-design](../archives/plans/2026-02-05-npu-worker-pool-design.md) | [#9879][i-fleet] | Load-balanced NPU pool with health loop + failover (`npu_worker_manager`, `autobot-npu-worker`) |
| Windows native NPU deployment | Shipped | [INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS](../research/INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS.md) | [#9879][i-fleet] | OpenVINO worker + Windows PowerShell deployment scripts (not research-only) |
| Release system (git-cliff) | Shipped | [release-system-design](../archives/plans/2026-03-01-release-system-design.md) | [#9879][i-fleet] | Automated release notes (`cliff.toml`, release.yml) + SLM package-update indicators |
| Service discovery & message bus | Partial | [service-discovery-design](../archives/plans/2026-02-02-service-discovery-design.md) | [#9879][i-fleet] | Message bus + mTLS shipped; dynamic service-discovery modules unwired (wire-in [#9893](https://github.com/mrveiss/AutoBot-AI/issues/9893)) |
| Configuration management | Partial | [CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN](../planning/CONFIGURATION_MANAGEMENT_IMPLEMENTATION_PLAN.md) | [#9879][i-fleet] | Env-var priority + validation shipped (`ssot_config`); full config hot-reload + cross-service settings-sync not present |

## Security & Governance

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Service auth enforcement | Shipped | [WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN](../planning/WEEK_3_ENFORCEMENT_MODE_DEPLOYMENT_PLAN.md) | [#9880][i-sec] | JWT service-to-service authentication across the fleet (registered middleware) |
| Secrets management | Shipped | [secrets_management_system](secrets_management_system.md) | [#9880][i-sec] | Encrypted, dual-scope (general + chat) secrets with audit log (cipher is Fernet, not AES-256 — see [#9894](https://github.com/mrveiss/AutoBot-AI/issues/9894)) |

## Platform Extensibility

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Plugin SDK | Shipped | [plugin-sdk-required-env](../superpowers/plans/2026-05-05-plugin-sdk-required-env.md) | [#9881][i-ext] | `plugin_sdk` + `plugin_manager` API (install/load/enable/env-status) + core plugins |
| MCP agent workflows | Shipped | [mcp_agent_workflows](../examples/mcp_agent_workflows/README.md) | [#9881][i-ext] | Four runnable example workflows (code analysis, research, VNC monitoring) |
| Language switcher (i18n) | Shipped | [language-switcher](../superpowers/plans/2026-04-07-language-switcher.md) | [#9881][i-ext] | vue-i18n, 11 locales (incl. RTL), `LanguageSwitcher.vue` + settings panel |

## Emerging Surfaces

| Capability | Status | Design doc | Issue | What it does |
|------------|--------|------------|-------|--------------|
| Live Canvas | Shipped | [live-canvas-phase1](../superpowers/plans/2026-05-16-live-canvas-phase1.md) | [#9882][i-emerge] | Vue canvas + streaming cells + export (md/json/html/pdf) (`/canvas`, `CanvasView.vue`) |
| AutoResearch | Shipped | [autoresearch-m3](../superpowers/plans/2026-04-01-autoresearch-m3.md) | [#9882][i-emerge] | Self-improving loop (meta-agent patch proposal + prompt optimizer) + dashboard (`/experiments`) |

---

## Gaps found during verification

Verification (2026-06-10) confirmed nearly all capabilities are real and wired. The
remaining gaps are tracked as discovery issues:

| Gap | Issue |
|-----|-------|
| Vision automation backend shipped, no frontend consumer | [#9890](https://github.com/mrveiss/AutoBot-AI/issues/9890) |
| Error-monitoring backend (12 endpoints) has no frontend | [#9891](https://github.com/mrveiss/AutoBot-AI/issues/9891) |
| Causal-inference engine (`/diagnostics/analyze-failure`) has no UI | [#9892](https://github.com/mrveiss/AutoBot-AI/issues/9892) |
| Service-discovery modules written but unwired (zero callers) | [#9893](https://github.com/mrveiss/AutoBot-AI/issues/9893) |
| Secrets cipher: doc says AES-256-GCM, code is Fernet (AES-128) | [#9894](https://github.com/mrveiss/AutoBot-AI/issues/9894) |

Smaller notes: *Advanced code intelligence* has all sub-analyzers shipped except
**semantic NL code search** (still planned); *Configuration management* lacks full config
hot-reload + cross-service settings-sync; *Memory graph semantic search* is a service-layer
component with no public REST route (by design).

## Single home for feature docs

`docs/features/` is the **single canonical home** for feature documentation, and this
catalog is its **single registry** — the one place that indexes every capability. By
decision (#9872), this is a *registry-only* model: design specs that are dated/historical
stay in their zones (`archives/plans/`, `superpowers/plans/`, `planning/`, `research/`)
and this catalog links them. The genuine current feature docs already live in
`docs/features/`; archival/planning specs are intentionally **not** relocated, to keep the
zone taxonomy and the Obsidian graph intact.

## How this catalog was built

This catalog consolidates a sweep of the archived/planning/design/implementation
documentation zones for capabilities that were not reachable from [INDEX.md](../INDEX.md).
Pure refactors, CI plumbing, and internal test infrastructure were excluded. Per-feature
verification (with code evidence) is recorded in the issues linked above under [#9872][u].

## Related

- [Features Index](_index.md)
- [The AutoBot Platform Model](../architecture/PLATFORM_MODEL.md)
- [AutoBot LLC](../llc/_index.md)
- [Glossary](../GLOSSARY.md)

[u]: https://github.com/mrveiss/AutoBot-AI/issues/9872
[i-voice]: https://github.com/mrveiss/AutoBot-AI/issues/9874
[i-rag]: https://github.com/mrveiss/AutoBot-AI/issues/9875
[i-code]: https://github.com/mrveiss/AutoBot-AI/issues/9876
[i-vision]: https://github.com/mrveiss/AutoBot-AI/issues/9877
[i-auto]: https://github.com/mrveiss/AutoBot-AI/issues/9878
[i-fleet]: https://github.com/mrveiss/AutoBot-AI/issues/9879
[i-sec]: https://github.com/mrveiss/AutoBot-AI/issues/9880
[i-ext]: https://github.com/mrveiss/AutoBot-AI/issues/9881
[i-emerge]: https://github.com/mrveiss/AutoBot-AI/issues/9882
[i-llc]: https://github.com/mrveiss/AutoBot-AI/issues/9883
[i-analytics]: https://github.com/mrveiss/AutoBot-AI/issues/9884
[i-trans]: https://github.com/mrveiss/AutoBot-AI/issues/9885
