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
  - ISO 42001
  - ISO 14001
  - ISO/IEC 42001
status: current
---

# EU AI Act & Governance Fit

> **Freshness:** current — 2026-09-14, filed under #16733. Describes what governance
> infrastructure exists in the codebase today and what does not. Not legal advice, and not a
> compliance certification — deployers remain responsible for classifying their own use case
> and meeting the obligations that follow from that classification. ISO 42001 and ISO 14001
> sections added the same day, same rule: cite what exists, state what doesn't, claim no
> certification.

This document states plainly what AutoBot's architecture already supports toward EU AI Act
(Regulation (EU) 2024/1689) governance obligations, and what it does not, and does the same for
two ISO management-system standards that come up in the same conversations — ISO/IEC 42001 (AI
management systems) and ISO 14001 (environmental management). Every claim below cites the file
it is based on. Where nothing exists yet, that is stated as a gap, not implied as done.

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

## ISO/IEC 42001 (AI management systems) fit

ISO/IEC 42001:2023 is the first international standard for an AI management system (AIMS) —
organizational processes for governing the AI lifecycle: risk management, roles and
responsibilities, monitoring, and continual improvement. It comes up alongside the EU AI Act
often because a working AIMS is one of the more direct ways to produce the governance evidence
the Act expects — but the two are independent: one is regulation, the other a voluntary
management-system standard with its own separate certification path.

| AIMS-relevant area | What exists today | Evidence |
|---|---|---|
| Governance & audit trail | Same compliance manager as the EU AI Act section above — audit logging, retention, consent tracking | `autobot-backend/security/enterprise/compliance_manager.py` |
| Risk-scoped access control | A capability-scoped plugin system with trust tiers, an approval flow, and an audit log — the closest thing to an AI-risk-gated process today, though scoped to plugins, not every AI decision the platform makes | `autobot_shared/plugin_sdk/capabilities.py`, `autobot-backend/plugin_manager.py` |
| Provider routing as risk mitigation | Fallback across LLM providers reduces single-vendor operational risk | `autobot-backend/llm_shared/provider_registry.py` |

**Missing for a real AIMS:** no documented AI policy, no AI-specific risk register, no tracked
lifecycle governance stages (design → validation → deployment → monitoring → decommission), and
no internal-audit process scoped to AI risk specifically, as opposed to the general GDPR/SOC2
audit above. No ISO 42001 certification exists or is claimed.

## ISO 14001 (environmental management) fit

ISO 14001 is an environmental management system (EMS) standard — it governs an organization's
environmental impact (energy, waste, resource use) and is not AI-specific. It's included here
only because it comes up in the same governance conversations, and the honest answer is narrower
than for the two standards above.

**The structural point, not a performance claim:** self-hosting puts hardware choice, power
source, and utilization inside the *operator's own* EMS boundary, instead of behind an opaque
third-party cloud vendor's unverifiable environmental claims. That is a difference in who
controls and can audit the variable. **It is not a claim that self-hosted inference uses less
energy than cloud inference** — that depends entirely on the operator's hardware and how much of
it sits idle, and AutoBot does not measure or claim either way.

**What's missing:** AutoBot has no power/energy telemetry, no carbon-accounting integration, and
no reporting feature of any kind toward an EMS. An operator pursuing ISO 14001 alignment would
need to instrument that themselves; nothing here does it for them.

## Bottom line

AutoBot's existing GDPR-oriented governance code and its self-hosted, provider-agnostic
architecture make EU AI Act and ISO 42001 governance evidence easier to produce than a
third-party SaaS AI integration would — because the operator controls the whole stack and
already has audit, retention, and RBAC primitives to build on. The ISO 14001 fit is weaker and
structural only (who controls the hardware/energy variables), not a measured environmental
benefit. None of this makes AutoBot, or any deployment built on it, compliant or certified by
itself. Classifying a specific use case and closing the gaps above remains the deployer's job.

---

## Related

- [The AutoBot Platform Model](PLATFORM_MODEL.md) — the architecture this document assesses
- [Glossary](../GLOSSARY.md)
