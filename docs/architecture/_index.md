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

## Overview

| Document | Description |
| --- | --- |
| [Platform Model](PLATFORM_MODEL.md) | What AutoBot is: core, SLM management layer, and modules |
| [README](README.md) | Architecture overview |
| [INDEX](INDEX.md) | Architecture index |
| [VISUAL_ARCHITECTURE](VISUAL_ARCHITECTURE.md) | Visual architecture diagram |
| [DISTRIBUTED_6VM_ARCHITECTURE](DISTRIBUTED_6VM_ARCHITECTURE.md) | 6-VM distributed deployment |
| [DISTRIBUTED_ARCHITECTURE](DISTRIBUTED_ARCHITECTURE.md) | Distributed architecture |
| [VM_ROLES](VM_ROLES.md) | VM role definitions — services, ports, Ansible groups |
| [NETWORK_TOPOLOGY](NETWORK_TOPOLOGY.md) | Network topology |
| [data-flows](data-flows.md) | Data flow diagrams |
| [dependency_injection](dependency_injection.md) | Dependency injection patterns |
| [auth](auth.md) | Authentication architecture |
| [counterfactual-reasoning](counterfactual-reasoning.md) | Counterfactual reasoning design |

## Agent System

| Document | Description |
| --- | --- |
| [AGENT_SYSTEM_ARCHITECTURE](AGENT_SYSTEM_ARCHITECTURE.md) | Agent system design |
| [agent-terminal](agent-terminal.md) | Agent terminal architecture |
| [Agent_Communication_Protocol](Agent_Communication_Protocol.md) | Agent communication protocol |
| [INDUSTRY_AGENT_PATTERNS_ANALYSIS](INDUSTRY_AGENT_PATTERNS_ANALYSIS.md) | Industry agent patterns |
| [COEXISTENCE_MATRIX](COEXISTENCE_MATRIX.md) | Agent coexistence matrix |

## API & Communication

| Document | Description |
| --- | --- |
| [COMMUNICATION_ARCHITECTURE](COMMUNICATION_ARCHITECTURE.md) | Communication architecture |
| [API_VS_DIRECT_QUICK_REFERENCE](API_VS_DIRECT_QUICK_REFERENCE.md) | API vs direct access |
| [CHAT_INFRASTRUCTURE_ACCESS_DESIGN](CHAT_INFRASTRUCTURE_ACCESS_DESIGN.md) | Chat infrastructure design |
| [LONG_RUNNING_OPERATIONS_ARCHITECTURE](LONG_RUNNING_OPERATIONS_ARCHITECTURE.md) | Long-running operations |

## Configuration & SSOT

| Document | Description |
| --- | --- |
| [SSOT_CONFIGURATION_ARCHITECTURE](SSOT_CONFIGURATION_ARCHITECTURE.md) | SSOT config architecture |
| [CONFIG_CONSOLIDATION_ANALYSIS](CONFIG_CONSOLIDATION_ANALYSIS.md) | Config consolidation analysis |
| [CONFIG_MIGRATION_IMPLEMENTATION](CONFIG_MIGRATION_IMPLEMENTATION.md) | Config migration implementation |

## Memory & Knowledge

| Document | Description |
| --- | --- |
| [AUTOBOT_MEMORY_GRAPH_ARCHITECTURE](AUTOBOT_MEMORY_GRAPH_ARCHITECTURE.md) | Memory graph architecture |
| [MEMORY_GRAPH_CHAT_INTEGRATION](MEMORY_GRAPH_CHAT_INTEGRATION.md) | Memory graph + chat |
| [VECTOR_STORE_MIGRATION](VECTOR_STORE_MIGRATION.md) | Vector store migration |
| [BACKGROUND_VECTORIZATION](BACKGROUND_VECTORIZATION.md) | Background vectorization |
| [EFFICIENT_INFERENCE_DESIGN](EFFICIENT_INFERENCE_DESIGN.md) | Efficient inference |

## Code Vectorization

| Document | Description |
| --- | --- |
| [CODE_VECTORIZATION_ARCHITECTURE](CODE_VECTORIZATION_ARCHITECTURE.md) | Code vectorization architecture |
| [CODE_VECTORIZATION_README](CODE_VECTORIZATION_README.md) | Code vectorization overview |
| [CODE_VECTORIZATION_DATA_FLOWS](CODE_VECTORIZATION_DATA_FLOWS.md) | Data flows |
| [CODE_VECTORIZATION_IMPLEMENTATION_PLAN](CODE_VECTORIZATION_IMPLEMENTATION_PLAN.md) | Implementation plan |
| [CODE_VECTORIZATION_PERFORMANCE_RISK](CODE_VECTORIZATION_PERFORMANCE_RISK.md) | Performance & risk |
| [CODE_VECTORIZATION_SUMMARY](CODE_VECTORIZATION_SUMMARY.md) | Summary |

## Terminal

| Document | Description |
| --- | --- |
| [TERMINAL_ARCHITECTURE_DIAGRAM](TERMINAL_ARCHITECTURE_DIAGRAM.md) | Terminal architecture diagram |
| [TERMINAL_ARCHITECTURE_DISTRIBUTED](TERMINAL_ARCHITECTURE_DISTRIBUTED.md) | Distributed terminal architecture |
| [TERMINAL_APPROVAL_WORKFLOW](TERMINAL_APPROVAL_WORKFLOW.md) | Terminal approval workflow |
| [TERMINAL_CONSOLIDATION_ANALYSIS](TERMINAL_CONSOLIDATION_ANALYSIS.md) | Consolidation analysis |
| [TERMINAL_INTEGRATION_ARCHITECTURE_VALIDATION](TERMINAL_INTEGRATION_ARCHITECTURE_VALIDATION.md) | Integration validation |

## Monitoring & Security

| Document | Description |
| --- | --- |
| [MONITORING_ARCHITECTURE](MONITORING_ARCHITECTURE.md) | Monitoring architecture |
| [Advanced_Monitoring_System](Advanced_Monitoring_System.md) | Advanced monitoring |
| [SECURITY_ASSESSMENT_WORKFLOW](SECURITY_ASSESSMENT_WORKFLOW.md) | Security assessment workflow |
| [PHASE_VALIDATION_SYSTEM](PHASE_VALIDATION_SYSTEM.md) | Phase validation |
| [BACKEND_CRITICAL_ISSUES_ARCHITECTURAL_ANALYSIS](BACKEND_CRITICAL_ISSUES_ARCHITECTURAL_ANALYSIS.md) | Critical issues analysis |

## Frontend & Roles

| Document | Description |
| --- | --- |
| [FRONTEND_ARCHITECTURE_ASSESSMENT](FRONTEND_ARCHITECTURE_ASSESSMENT.md) | Frontend architecture |
| [ROLE_ARCHITECTURE](ROLE_ARCHITECTURE.md) | Role architecture |

## Scaling & Migration

| Document | Description |
| --- | --- |
| [Scaling_Roadmap_and_Architecture_Evolution](Scaling_Roadmap_and_Architecture_Evolution.md) | Scaling roadmap |
| [Kubernetes_Migration_Strategy](Kubernetes_Migration_Strategy.md) | Kubernetes migration |
| [Async_System_Migration](Async_System_Migration.md) | Async migration |
| [Docker_Architecture_Documentation](Docker_Architecture_Documentation.md) | Docker architecture |
| [Docker_Architecture_Quick_Start](Docker_Architecture_Quick_Start.md) | Docker quick start |
| [UPDATE_FLOWS](UPDATE_FLOWS.md) | Update flows |
| [redis-schema](redis-schema.md) | Redis schema |
| [KB-ASYNC-014-COMPLETION-SUMMARY](KB-ASYNC-014-COMPLETION-SUMMARY.md) | KB async completion |
| [Performance_and_Security_Optimizations](Performance_and_Security_Optimizations.md) | Performance & security |

## Design Records

| Document | Description |
| --- | --- |
| [designs/ARCHITECTURE_DECISION_RECORD](designs/ARCHITECTURE_DECISION_RECORD.md) | Architecture decision record |
| [designs/EVENT_STREAM_SYSTEM_DESIGN](designs/EVENT_STREAM_SYSTEM_DESIGN.md) | Event stream design |
| [designs/KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN](designs/KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md) | Knowledge module enhancements |
| [designs/PARALLEL_TOOL_EXECUTION_DESIGN](designs/PARALLEL_TOOL_EXECUTION_DESIGN.md) | Parallel tool execution |
| [designs/PLANNER_MODULE_DESIGN](designs/PLANNER_MODULE_DESIGN.md) | Planner module design |
