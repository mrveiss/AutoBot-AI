---
tags:
  - index
  - reports
aliases:
  - Reports Index
---

# Session & Audit Reports

Point-in-time reports from sweeps, umbrella missions and audits. Each one is a record of
what a session found and shipped, kept for the evidence trail — they are **not** living
documentation and are not updated after the fact. For current behaviour, read
`docs/developer/` and `docs/architecture/`; for technology evaluations, read
[[_index|docs/research/]].

These files lived at the repository root until #14216 moved them here. A pre-commit guard
(`tools/lint/check_no_root_clutter.py`) now keeps the front door clear.

## Documents

| Document | Description |
| --- | --- |
| [[BUG_SWEEP_REPORT]] | Bug sweep of 2026-06-10 — findings and fixes off `Dev_new_gui` |
| [[DEDUP_REPORT]] | Code-duplication elimination pass — duplicate clusters found and consolidated |
| [[IMPLEMENTATION_REPORT]] | Causal relationship extractor — RAG semantic chunking, fact extraction, entity resolution (#3395) |
| [[LLC_SHIP_REPORT]] | AutoBot LLC module ship report (#9861) |
| [[MIGRATION_BASELINE_REPORT]] | Migration baseline captured across #10001 → #10026 |
| [[SESSION_9930_PHASE_C_PREREQ_REPORT_2026_06_26]] | Umbrella #9930 phase C — SSO secrets into the unified vault, plus rotation (2026-06-25 → 06-27) |
| [[TRIAGE_DELTA_REPORT]] | Triage delta of 2026-06-12 — tracker count and lifecycle movement |
| [[U7_DOCS_POSITIONING_REPORT]] | Umbrella #9926 — docs positioning mission report |
| [[UMBRELLA_9925_TRANSCRIBER_REPORT]] | Umbrella #9925 — Transcriber feature branch, security trio, code quality |
| [[UMBRELLA_9930_ENTERPRISE_AUTH_REPORT]] | Umbrella #9930 — enterprise auth (SSO/OIDC) session report |
| [[UMBRELLA_9931_RECOVERY_REPORT]] | Umbrella #9931 — codebase recovery, closed-unmerged PR archaeology |
| [[UMBRELLA_PLAN]] | Open-tracker umbrella plan of 2026-06-11 — dependency graph and dispatch waves |
| [[WIRING_AUDIT_REPORT]] | API wiring audit (#9851) — frontend/backend contract coverage |
| `missing_dep_sites.txt` | 41 `_MissingDep` placeholder sites — raw scan output, kept as the input list for the optional-dependency cleanup |
