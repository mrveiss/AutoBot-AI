---
tags:
  - index
  - research
aliases:
  - Research Index
---

# Research Documentation

Research reports covering hardware integration, system conflicts, and technology evaluations.

## Documents

| Document | Description |
| --- | --- |
| [[INTEL_NPU_WINDOWS_DEPLOYMENT_ANALYSIS]] | Intel NPU Windows deployment analysis and feasibility |
| [[lean-hardware-model-loading]] | Large-model inference on lean hardware — target architecture and capability audit of `llm_shared/optimization/` (#13030) |
| [[REDIS_OWNERSHIP_CONFLICT_RESEARCH_REPORT]] | Redis ownership conflict investigation and resolution research |
| [[visual-operations-blueprint]] | Visual operations blueprint — capability research and Company OS audit; GUI-only adoption decision, canvas already owned, org-chart human branch unreachable (#13935) |
| [[canvas-grid-rendering-review]] | Canvas and grid rendering review — techniques audit of `WorkflowCanvas`, the LLC Gantt and the graph charts; grid/geometry/edge-index gaps fixed, motion and safe-area gaps open (#14765, #14766, #14767, #14769, #14770, #14771) |
| [[connector-credential-egress-audit]] | Connector, credential and egress layer audit — 2 live OAuth bugs, 2 fail-open guards, secrets-manager bypass (#13623, #13643) |
| [[tiered-context-ab-13689]] | Tiered L0–L4 context stack — #5066 A/B result, **corrected**: measured against test doubles, 3 of 5 layers cannot render, flag reverted to off (#13689, #13742, #13866) |
| [[layered-agent-memory-and-context-offload]] | Layered agent memory + symbolic context offload — tiered L0–L4 stack built but never ran, 2 of 5 layers structurally disconnected, memory plane untenanted (#13685) |
| [[desktop-worker-harness-approval-and-compaction]] | Desktop worker-agent harness comparison — our SSRF guard, command-risk and guard-profile work is ahead; gaps are a success-shaped compaction failure, an ungated outbound gateway seam, approvals unreachable when nobody is at the screen, and four unreconciled tool-classification planes (#14065–#14068) |
| [[agent-harness-guard-and-context-audit]] | Agent harness comparison — our loop guards are stronger, but guard input is un-normalized, context windows are a static 4096 fallback, ingest has no bot-self filter, and `AgentLoop` has no production caller (#14027–#14031) |
| [[model-hardware-standard]] | Anthropic Model Hardware Standard (MHS) — source analysis + AutoBot comparison; spec not public and metrics all self-reported, but three of its four transferable patterns land on AutoBot code already half-built: `MCPBridgeManifest.resource_limits` declared but unenforced, `ToolResult.error` a bare string while `classify_error` stays loop-internal, and the entire remote/Slack approval path has no production caller |
| [[gpu-kernel-authoring-runtime]] | A GPU kernel-authoring runtime — source analysis + AutoBot comparison; Python functions JIT-compiled to native CPU code or GPU PTX, with the transferable pattern being the author-once/compile-per-target split rather than the numerical domain itself, which is physics and geometry rather than agent workloads |
| [[RES_efficient-inference]] | Latency-focused LLM inference optimization architecture — techniques that improve latency *and* memory together, rejecting the layer-sharding trade that took inference from 500ms to 2000ms |
| [[RES_research-agent-precision-efficiency]] | Research agent precision and efficiency — every research run starts cold and synthesized answers are un-cited template strings, while the KB already provides the fact store with provenance, verification and dedup that would fix it (#1252, #12621, #12622, #12625) |
| [[agent-host-and-agent-client-protocols]] | Agent Host Protocol and Agent Client Protocol — source analysis; two layers of one stack rather than competitors. Phase 1 complete, AutoBot comparison not started (#11843, #12366) |
| [[email-reading-capability-audit]] | Email reading capability audit — whether AutoBot can read email, and what the Company OS gains from giving the CEO agent an address (#10533, #13228, #13250, #13421, #13587, #13588) |
| [[loop-velocity-patterns]] | Why commit progress feels slow — measured loop/subagent patterns on `Dev_new_gui`; throughput is not the problem at ~30 commits/day and a 2.09h median PR open-to-merge (#15294, #15295, #15296, #15306, #15309, #15376) |

## Related Sections

- [[../analysis/_index\|Analysis]] — Analysis based on research
- [[../design/_index\|Design]] — Design informed by research
- [[../discovery/_index\|Discovery]] — Discovery reports
