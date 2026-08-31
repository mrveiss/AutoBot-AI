---
tags:
  - index
  - architecture
aliases:
  - Architecture Index
---

# Architecture Documentation

> Start here: **[The AutoBot Platform Model](PLATFORM_MODEL.md)** — the three-layer
> picture (platform core → SLM management layer → modules) that the rest of these
> documents build on.

Regenerated 2026-08-30 as part of #15192 — analysis, research, design and planning documents
that previously lived here moved out per the #15190 convention; see "Moved out of this folder"
below for the redirect table. Every document remaining here (and every moved one) now carries a
dated `> **Freshness:**` marker.

## Overview

| Document | Description |
| --- | --- |
| [Platform Model](PLATFORM_MODEL.md) | What AutoBot is: core, SLM management layer, and modules |
| [README](README.md) | Architecture overview |
| [INDEX](INDEX.md) | Code-vectorization sub-index (historical) |
| [VISUAL_ARCHITECTURE](VISUAL_ARCHITECTURE.md) | Visual architecture diagram |
| [DISTRIBUTED_6VM_ARCHITECTURE](DISTRIBUTED_6VM_ARCHITECTURE.md) | 6-VM distributed deployment (historical completion record) |
| [DISTRIBUTED_ARCHITECTURE](DISTRIBUTED_ARCHITECTURE.md) | Distributed architecture |
| [VM_ROLES](VM_ROLES.md) | VM role definitions — services, ports, Ansible groups |
| [NETWORK_TOPOLOGY](NETWORK_TOPOLOGY.md) | Network topology |
| [data-flows](data-flows.md) | Data flow diagrams |
| [dependency_injection](dependency_injection.md) | Dependency injection patterns |
| [auth](auth.md) | Authentication architecture |
| [counterfactual-reasoning](counterfactual-reasoning.md) | Counterfactual reasoning design |
| [system-diagram](system-diagram.md) | System diagram |

## Agent System

| Document | Description |
| --- | --- |
| [AGENT_SYSTEM_ARCHITECTURE](AGENT_SYSTEM_ARCHITECTURE.md) | Agent system design |
| [agent-terminal](agent-terminal.md) | Agent terminal architecture |
| [Agent_Communication_Protocol](Agent_Communication_Protocol.md) | Agent communication protocol |
| [COEXISTENCE_MATRIX](COEXISTENCE_MATRIX.md) | Agent coexistence matrix |
| [agent-belief-state](agent-belief-state.md) | Belief-state prototype (Phase 1) |
| [agent-belief-state-benchmark](agent-belief-state-benchmark.md) | Belief-state A/B benchmark results (historical) |
| [async-work](async-work.md) | Async work architecture |
| [shared-runtime-bag](shared-runtime-bag.md) | Shared runtime bag |
| [causal-error-recovery](causal-error-recovery.md) | Causal error recovery |
| [causal-inference-algorithms](causal-inference-algorithms.md) | Causal inference algorithms |

## API & Communication

| Document | Description |
| --- | --- |
| [COMMUNICATION_ARCHITECTURE](COMMUNICATION_ARCHITECTURE.md) | Communication architecture |
| [API_VS_DIRECT_QUICK_REFERENCE](API_VS_DIRECT_QUICK_REFERENCE.md) | API vs direct access |
| [LONG_RUNNING_OPERATIONS_ARCHITECTURE](LONG_RUNNING_OPERATIONS_ARCHITECTURE.md) | Long-running operations |
| [chat-state-ssot](chat-state-ssot.md) | Chat state SSOT design |

## Configuration & SSOT

| Document | Description |
| --- | --- |
| [SSOT_CONFIGURATION_ARCHITECTURE](SSOT_CONFIGURATION_ARCHITECTURE.md) | SSOT config architecture (historical — see freshness note) |

## Memory & Knowledge

| Document | Description |
| --- | --- |
| [AUTOBOT_MEMORY_GRAPH_ARCHITECTURE](AUTOBOT_MEMORY_GRAPH_ARCHITECTURE.md) | Memory graph architecture (superseded — see freshness note) |
| [MEMORY_GRAPH_CHAT_INTEGRATION](MEMORY_GRAPH_CHAT_INTEGRATION.md) | Memory graph + chat (historical completion record) |
| [VECTOR_STORE_MIGRATION](VECTOR_STORE_MIGRATION.md) | Vector store migration (historical completion record) |
| [BACKGROUND_VECTORIZATION](BACKGROUND_VECTORIZATION.md) | Background vectorization |

## Code Vectorization (superseded by shipped implementation — see each file's freshness note)

| Document | Description |
| --- | --- |
| [CODE_VECTORIZATION_ARCHITECTURE](CODE_VECTORIZATION_ARCHITECTURE.md) | Code vectorization architecture |
| [CODE_VECTORIZATION_README](CODE_VECTORIZATION_README.md) | Code vectorization overview |
| [CODE_VECTORIZATION_DATA_FLOWS](CODE_VECTORIZATION_DATA_FLOWS.md) | Data flows |
| [CODE_VECTORIZATION_PERFORMANCE_RISK](CODE_VECTORIZATION_PERFORMANCE_RISK.md) | Performance & risk |
| [CODE_VECTORIZATION_SUMMARY](CODE_VECTORIZATION_SUMMARY.md) | Summary |

The implementation plan moved to [`docs/planning/CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md`](../planning/CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md).

## Terminal

| Document | Description |
| --- | --- |
| [TERMINAL_ARCHITECTURE_DIAGRAM](TERMINAL_ARCHITECTURE_DIAGRAM.md) | Terminal architecture diagram |
| [TERMINAL_ARCHITECTURE_DISTRIBUTED](TERMINAL_ARCHITECTURE_DISTRIBUTED.md) | Distributed terminal architecture |
| [TERMINAL_APPROVAL_WORKFLOW](TERMINAL_APPROVAL_WORKFLOW.md) | Terminal approval workflow |
| [TERMINAL_INTEGRATION_ARCHITECTURE_VALIDATION](TERMINAL_INTEGRATION_ARCHITECTURE_VALIDATION.md) | Integration validation (historical) |

Terminal consolidation analysis moved to [`docs/analysis/ANA_terminal-consolidation-2025-11-09.md`](../analysis/ANA_terminal-consolidation-2025-11-09.md).

## Monitoring & Security

| Document | Description |
| --- | --- |
| [MONITORING_ARCHITECTURE](MONITORING_ARCHITECTURE.md) | Monitoring architecture |
| [Advanced_Monitoring_System](Advanced_Monitoring_System.md) | Advanced monitoring |
| [SECURITY_ASSESSMENT_WORKFLOW](SECURITY_ASSESSMENT_WORKFLOW.md) | Security assessment workflow |
| [PHASE_VALIDATION_SYSTEM](PHASE_VALIDATION_SYSTEM.md) | Phase validation |
| [REDIS_SERVICE_MANAGEMENT_ARCHITECTURE](REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md) | Redis service management (partially superseded — see freshness note, #15198) |
| [npu-pipeline-parallelism](npu-pipeline-parallelism.md) | NPU pipeline parallelism |
| [redis-schema](redis-schema.md) | Redis schema |

Backend critical-issues analysis moved to
[`docs/analysis/ANA_backend-critical-issues-architectural-2025-10-05.md`](../analysis/ANA_backend-critical-issues-architectural-2025-10-05.md)
(deployment-blocked claim resolved — see that document's freshness note).

## Frontend & Roles

| Document | Description |
| --- | --- |
| [FRONTEND_ARCHITECTURE_ASSESSMENT](FRONTEND_ARCHITECTURE_ASSESSMENT.md) | Frontend architecture assessment (historical; classification open, see #15190) |
| [ROLE_ARCHITECTURE](ROLE_ARCHITECTURE.md) | Role architecture |

## Scaling & Migration

| Document | Description |
| --- | --- |
| [Scaling_Roadmap_and_Architecture_Evolution](Scaling_Roadmap_and_Architecture_Evolution.md) | Scaling roadmap |
| [Async_System_Migration](Async_System_Migration.md) | Async migration |
| [Docker_Architecture_Documentation](Docker_Architecture_Documentation.md) | Docker architecture |
| [Docker_Architecture_Quick_Start](Docker_Architecture_Quick_Start.md) | Docker quick start |
| [UPDATE_FLOWS](UPDATE_FLOWS.md) | Update flows |
| [KB-ASYNC-014-COMPLETION-SUMMARY](KB-ASYNC-014-COMPLETION-SUMMARY.md) | KB async completion (historical completion record) |
| [Performance_and_Security_Optimizations](Performance_and_Security_Optimizations.md) | Performance & security |

Kubernetes migration strategy moved to [`docs/planning/Kubernetes_Migration_Strategy.md`](../planning/Kubernetes_Migration_Strategy.md).

## Moved out of this folder (#15192, #15190 convention)

| Was here | Now at | Kind |
| --- | --- | --- |
| `BACKEND_CRITICAL_ISSUES_ARCHITECTURAL_ANALYSIS.md` | [`docs/analysis/ANA_backend-critical-issues-architectural-2025-10-05.md`](../analysis/ANA_backend-critical-issues-architectural-2025-10-05.md) | analysis |
| `CONFIG_CONSOLIDATION_ANALYSIS.md` | [`docs/analysis/ANA_config-consolidation-2025-11-17.md`](../analysis/ANA_config-consolidation-2025-11-17.md) | analysis |
| `TERMINAL_CONSOLIDATION_ANALYSIS.md` | [`docs/analysis/ANA_terminal-consolidation-2025-11-09.md`](../analysis/ANA_terminal-consolidation-2025-11-09.md) | analysis |
| `INDUSTRY_AGENT_PATTERNS_ANALYSIS.md` | [`docs/analysis/ANA_industry-agent-patterns-2025-12-28.md`](../analysis/ANA_industry-agent-patterns-2025-12-28.md) | analysis |
| `EFFICIENT_INFERENCE_DESIGN.md` | [`docs/research/RES_efficient-inference.md`](../research/RES_efficient-inference.md) | research (self-declared) |
| `RESEARCH_AGENT_PRECISION_EFFICIENCY_DESIGN.md` | [`docs/research/RES_research-agent-precision-efficiency.md`](../research/RES_research-agent-precision-efficiency.md) | research (self-declared) |
| `CHAT_INFRASTRUCTURE_ACCESS_DESIGN.md` | [`docs/design/CHAT_INFRASTRUCTURE_ACCESS_DESIGN.md`](../design/CHAT_INFRASTRUCTURE_ACCESS_DESIGN.md) | design |
| `TIMEOUT_CONFIGURATION_PROMETHEUS_METRICS_DESIGN.md` | [`docs/design/TIMEOUT_CONFIGURATION_PROMETHEUS_METRICS_DESIGN.md`](../design/TIMEOUT_CONFIGURATION_PROMETHEUS_METRICS_DESIGN.md) | design |
| `designs/ARCHITECTURE_DECISION_RECORD.md` | [`docs/design/ARCHITECTURE_DECISION_RECORD.md`](../design/ARCHITECTURE_DECISION_RECORD.md) | design |
| `designs/CODE_EXECUTION_AGENT_MODE_DESIGN.md` | [`docs/design/CODE_EXECUTION_AGENT_MODE_DESIGN.md`](../design/CODE_EXECUTION_AGENT_MODE_DESIGN.md) | design |
| `designs/EVENT_STREAM_SYSTEM_DESIGN.md` | [`docs/design/EVENT_STREAM_SYSTEM_DESIGN.md`](../design/EVENT_STREAM_SYSTEM_DESIGN.md) | design |
| `designs/KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md` | [`docs/design/KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md`](../design/KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md) | design |
| `designs/PARALLEL_TOOL_EXECUTION_DESIGN.md` | [`docs/design/PARALLEL_TOOL_EXECUTION_DESIGN.md`](../design/PARALLEL_TOOL_EXECUTION_DESIGN.md) | design |
| `designs/PLANNER_MODULE_DESIGN.md` | [`docs/design/PLANNER_MODULE_DESIGN.md`](../design/PLANNER_MODULE_DESIGN.md) | design |
| `CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md` | [`docs/planning/CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md`](../planning/CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md) | planning |
| `CONFIG_MIGRATION_IMPLEMENTATION.md` | [`docs/planning/CONFIG_MIGRATION_IMPLEMENTATION.md`](../planning/CONFIG_MIGRATION_IMPLEMENTATION.md) | planning |
| `Kubernetes_Migration_Strategy.md` | [`docs/planning/Kubernetes_Migration_Strategy.md`](../planning/Kubernetes_Migration_Strategy.md) | planning |

## Not relocated despite a completion/assessment shape (open decisions, see #15190/#15191)

`KB-ASYNC-014-COMPLETION-SUMMARY.md`, `MEMORY_GRAPH_CHAT_INTEGRATION.md`, `VECTOR_STORE_MIGRATION.md`
and `DISTRIBUTED_6VM_ARCHITECTURE.md` are completion records; relocating them out of this folder is
#15191's scope (the changelog/completion-record overload), not #15192's. `FRONTEND_ARCHITECTURE_ASSESSMENT.md`,
`TERMINAL_INTEGRATION_ARCHITECTURE_VALIDATION.md` and `agent-belief-state-benchmark.md` have an
open `*_ASSESSMENT.md`/validation-record classification question recorded on #15190 that has not been
settled — left in place rather than guessed at.
