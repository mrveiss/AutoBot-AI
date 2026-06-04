---
tags: [type/reference, status/current]
date: 2026-06-04
---

# Changelog — Feature Records Index

Post-implementation records of what was built in significant PRs. Each captures *what* was built, *how*, and *why* — preserved as historical context even after the feature is fully merged and stable.

**Format:** `YYYY-MM-DD-feature-name.md`

**Not for:** Minor bug fixes, dependency bumps, config changes. Those belong in git commit messages.

**For:** New subsystems, architectural changes, multi-file feature implementations.

---

## 2026

| Doc | Feature | Issue |
|---|---|---|
| [[2026-04-10-causal-relationship-extractor]] | CausalRelationshipExtractor — ECL knowledge pipeline | #3395 |
| [[2026-04-10-causal-inference-engine]] | CausalInferenceEngine — production root-cause analysis | #4069 |
| [[2026-04-10-causal-reasoning]] | Causal reasoning patterns for agent system | — |
| [[2026-04-10-stratified-agent-comparison]] | Stratified agent comparison (confounder-controlled evaluation) | — |
| [[2026-04-10-mcp-tool-distribution]] | MCP tool distribution across 29-agent roster | #3386 |

## 2025

| Doc | Feature | Issue |
|---|---|---|
| [[2025-10-04-xterm-upgrade]] | xterm.js v5 terminal upgrade — BaseXTerminal, PTY separation | — |

---

## Adding a Feature Record

Write after the PR is merged. Include:
- Issue number and link
- What files were created/modified (brief)
- Design decisions made during implementation
- Known limitations or follow-up issues filed

This is a record, not a spec. Write in past tense.
