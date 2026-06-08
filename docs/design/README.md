---
tags: [type/reference, status/current]
date: 2026-06-04
---

# Design Docs — Index

Pre-implementation design documents. Each captures *why* a feature was designed the way it was — the problem, the options considered, and the decision made. These are preserved as historical record even after the feature ships.

**Format:** `YYYY-MM-DD-feature-name.md`

**Tag:** `type/architecture` + `status/current` (if the design is still accurate) or `status/stale` (if the implementation diverged).

---

## 2026

| Doc | Feature | Issue |
|---|---|---|
| [[2026-04-10-causal-error-recovery]] | Causal Error Recovery system design | #2154 |
| [[2026-04-10-counterfactual-reasoning]] | CounterfactualReasoner — three-tier prediction strategy | #4069 |

---

## Adding a Design Doc

Write the design doc before or during implementation. Include:
- **Problem** — what you're solving and why
- **Options considered** — at least two alternatives
- **Decision** — which option was chosen and why
- **Trade-offs** — what you're giving up

Link the design doc from the GitHub issue before coding starts.
