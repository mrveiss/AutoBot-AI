---
tags:
  - architecture
  - governance
  - compliance
  - positioning
aliases:
  - EU AI Act
  - AI Act Fit
  - Governance Fit
status: current
---

# EU AI Act & Governance Fit

> **Freshness:** current — 2026-09-14, filed under #16733. Describes what governance
> infrastructure exists in the codebase today and what does not. Not legal advice, and not a
> compliance certification — deployers remain responsible for classifying their own use case
> and meeting the obligations that follow from that classification.

This document states plainly what AutoBot's architecture already supports toward EU AI Act
(Regulation (EU) 2024/1689) governance obligations, and what it does not. Every claim below cites
the file it is based on. Where nothing exists yet, that is stated as a gap, not implied as done.

---

## Why this matters for a self-hosted platform

The EU AI Act's obligations phase in through 2025–2027 (prohibited practices from February 2025,
general-purpose AI model obligations from August 2025, high-risk system obligations from August
2026) and apply regardless of which vendor's AI a deployer uses. Self-hosting does not exempt an
organization from the Act — but it changes **who carries which obligation**, and how directly the
evidence for compliance can be produced, compared to routing the same workload through a
third-party SaaS API you cannot inspect.

## What already exists in the codebase

| Obligation area (informal, not a legal citation) | What exists today | Evidence |
|---|---|---|
| Data governance & audit logging | A real compliance manager: audit logging, retention policies, consent tracking for GDPR/SOC2/ISO27001 | `autobot-backend/security/enterprise/compliance_manager.py` |
| Data subject rights / privacy controls | Memory privacy controls and retention-policy models/migrations | `autobot-backend/api/memory_privacy.py`, `autobot-backend/user_management/models/retention_policy.py` |
| Data residency | Self-hosted deployment keeps data (and the audit trail proving where it went) inside the operator's own jurisdiction, avoiding the cross-border-transfer questions a non-EU-hosted SaaS API raises | Architectural — see [Platform Model](PLATFORM_MODEL.md) |
| Provider vs. deployer exposure | The provider-agnostic LLM gateway means the operator calls or self-hosts a model rather than training one — placing the heavier general-purpose-AI-model obligations (training-data summaries, systemic-risk documentation) on whoever trained the model, not on the AutoBot operator, in the common case of using an unmodified model | `autobot-backend/llm_shared/provider_registry.py` |
| Human oversight | Core governance primitives — RBAC, review gates, budgets — that a higher-risk deployment's human-oversight design would build on | Described in [Platform Model](PLATFORM_MODEL.md#1-platform-core--small-solid-yours) |

## What does not exist yet — stated as a gap, not implied as done

- **No risk-tier classifier.** Nothing in the codebase determines whether a given module or
  use case (e.g. an AutoBot LLC agent making a decision with legal or safety effect) falls under
  a higher-risk category. That classification is the deployer's responsibility today, with no
  tooling to help.
- **No technical-documentation generator.** The Act's higher-risk obligations expect structured
  technical documentation; AutoBot has no feature that produces it.
- **No log schema shaped to the Act's specific record-keeping requirements.** The existing audit
  logging (`compliance_manager.py`) was built for GDPR/SOC2/ISO27001, not authored against the
  Act's logging article specifically — it is a real starting point, not a finished mapping.
- **No conformity-assessment or CE-marking tooling** of any kind.

## Bottom line

AutoBot's existing GDPR-oriented governance code and its self-hosted, provider-agnostic
architecture make EU AI Act governance obligations easier to meet than a third-party SaaS AI
integration would — because the operator controls the whole stack and already has audit,
retention, and RBAC primitives to build on. It does not make AutoBot, or any deployment built on
it, compliant by itself. Classifying a specific use case and closing the gaps above remains the
deployer's job.

---

## Related

- [The AutoBot Platform Model](PLATFORM_MODEL.md) — the architecture this document assesses
- [Glossary](../GLOSSARY.md)
