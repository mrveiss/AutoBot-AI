# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the AutoBot platform.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences. ADRs provide a historical record of architectural decisions that have shaped the AutoBot platform.

## Why ADRs?

- **Historical Context**: Understand why decisions were made
- **Onboarding**: Help new team members understand the architecture
- **Prevent Regression**: Avoid revisiting decisions without understanding original context
- **Documentation**: Living documentation that evolves with the project

## ADR Format

Each ADR follows a consistent template (see [template.md](template.md)):

1. **Title**: Short descriptive title with ADR number
2. **Status**: Proposed, Accepted, Deprecated, or Superseded
3. **Date**: When the decision was made
4. **Context**: What is the issue we're addressing?
5. **Decision**: What is the change we're making?
6. **Consequences**: What are the results of this decision?
7. **Implementation Notes**: Technical details and code references

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](001-distributed-vm-architecture.md) | Distributed 6-VM Architecture | Accepted | 2025-01-01 |
| [ADR-002](002-redis-database-separation.md) | Redis Database Separation Strategy | Accepted | 2025-01-01 |
| [ADR-003](003-npu-integration-strategy.md) | NPU Hardware Acceleration Integration | Accepted | 2025-01-01 |
| [ADR-004](004-chat-workflow-architecture.md) | Chat Workflow and Message Processing | Accepted | 2025-01-01 |
| [ADR-005](005-single-frontend-mandate.md) | Single Frontend Server Mandate | Accepted | 2025-01-01 |

## Creating a New ADR

1. Copy `template.md` to a new file with format `NNN-short-title.md`
2. Fill in all sections of the template
3. Add entry to the ADR Index above
4. Submit for review

## Superseding an ADR

When a decision is revised:

1. Update the old ADR's status to "Superseded by ADR-NNN"
2. Create a new ADR that references the superseded ADR
3. Explain why the original decision is being changed

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
