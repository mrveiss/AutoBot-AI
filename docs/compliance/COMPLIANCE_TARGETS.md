# Compliance Targets

> **AutoBot does not claim compliance with, or certification against, any standard or
> regulation listed here.** These are the standards we are **working towards**. Each
> row names the target's **source** (the body that publishes it, with the official
> reference), its **basis** (why it is a target), how far we are, and where the open
> work is tracked. A reader can check progress against the code instead of trusting a
> label.

This register is the one place AutoBot names its compliance targets. New or revised
documents (README, architecture notes, sales material) link here rather than restate a
target's status in their own words. Older documents still carry such wording (for
example "WCAG 2.1 AA compliant" in `docs/implementation/ISSUE_753_FINAL_REPORT.md` and
"WCAG 2.1 compliant" in `docs/features/file_upload_improvements.md`); where they disagree
with this register, this register wins and their wording is not a compliance claim. The
programme is tracked in umbrella
[#19113](https://github.com/mrveiss/AutoBot-AI/issues/19113).

## How to read this

| Column | Meaning |
|---|---|
| **Source** | The body that publishes the target and its official designation. A link is given only where it was confirmed to resolve; otherwise cite the designation and look it up in the publisher's own catalogue. |
| **Basis** | Why it is a target: an owner decision (dated), the law applies to the product or its users, an engineering baseline we chose, or a readiness review. |
| **Track** | **A (vendor):** AutoBot itself must meet it. **B (customer enabler):** the obligation sits with the customer (e.g. a financial entity under DORA, a data controller under GDPR). AutoBot ships the features and evidence they need for *their* audit. |

| Status | Meaning |
|---|---|
| **Adopting** | Owner decision to build a programme towards it. Gaps are verified against the code and tracked as issues. |
| **Engineering baseline** | Used as a technical yardstick for how we build. Findings are verified and filed; no formal programme. |
| **Assessed** | A readiness review was done. Whether to adopt is still an owner decision. |

## Adopting

| Target | Source | Basis | Track | Scope for AutoBot | Tracking |
|---|---|---|---|---|---|
| ISO/IEC 5230:2020, OpenChain specification (licence compliance) | ISO/IEC JTC 1, published by ISO; programme home: [OpenChain Project](https://openchainproject.org/) | Owner decision 2026-10-21 | A | Open-source licence policy, roles, SBOM, licence notices per release | [#19113](https://github.com/mrveiss/AutoBot-AI/issues/19113) (A1–A3, A9, A11) |
| ISO/IEC 18974:2023, OpenChain security assurance specification | ISO/IEC JTC 1, published by ISO; programme home: [OpenChain Project](https://openchainproject.org/) | Owner decision 2026-10-21 | A | Known-vulnerability handling for open-source components: SBOM, register, VEX, scanning | [#19113](https://github.com/mrveiss/AutoBot-AI/issues/19113) (A4–A8, A10) |
| ISO/IEC 25010:2023, systems and software quality models (SQuaRE) | ISO/IEC JTC 1/SC 7, published by ISO | Owner decision 2026-10-21 | A | Map existing guards, ratchets and tests onto the quality characteristics; accessibility gate | [#19113](https://github.com/mrveiss/AutoBot-AI/issues/19113) (A13) |
| DORA (Digital Operational Resilience Act), Regulation (EU) 2022/2554 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2022/2554/oj) | Owner decision 2026-10-21: EU financial-sector firms are potential customers | B | Recovery policy, restore drills, incident records and export, exit/portability, assurance pack | [#19113](https://github.com/mrveiss/AutoBot-AI/issues/19113) (B1–B11) |

## Applies by law to the product or its users

| Target | Source | Basis | Track | Notes | Tracking |
|---|---|---|---|---|---|
| Cyber Resilience Act, Regulation (EU) 2024/2847 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/2847/oj) | Applies to products with digital elements placed on the EU market | A | Manufacturer/steward role, SBOM and vulnerability-reporting duties | [#19106](https://github.com/mrveiss/AutoBot-AI/issues/19106) |
| GDPR, Regulation (EU) 2016/679 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | Applies to customers processing personal data | B | Configurable retention (no framework-labelled defaults), erasure across every store, export | [#16846](https://github.com/mrveiss/AutoBot-AI/issues/16846), [#18074](https://github.com/mrveiss/AutoBot-AI/issues/18074), [#19093](https://github.com/mrveiss/AutoBot-AI/issues/19093) |
| AI Act, Regulation (EU) 2024/1689 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) | Applies to AI systems placed on or used in the EU market; obligations depend on the use case | A/B | See [EU AI Act, NIS2 & Governance Fit](../architecture/EU_AI_GOVERNANCE.md) for covered vs gap | owner decision pending on programme scope |
| NIS2, Directive (EU) 2022/2555 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/dir/2022/2555/oj) | Applies to customers in essential/important sectors | B | Customers need incident handling and supply-chain evidence | covered by the DORA track items where they overlap |

## Engineering baselines

| Target | Source | Basis | What we use it for | Tracking |
|---|---|---|---|---|
| OWASP Top 10 for LLM Applications 2026 | OWASP Foundation, GenAI Security Project; [genai.owasp.org](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) | Engineering baseline: agent-platform risks | Prompt injection, excessive agency, output handling | [#19118](https://github.com/mrveiss/AutoBot-AI/issues/19118) |
| OWASP ASVS 5.0 (Application Security Verification Standard) | OWASP Foundation; [owasp.org](https://owasp.org/www-project-application-security-verification-standard/) | Engineering baseline | Web/API security verification checklist | — |
| NIST SP 800-218, Secure Software Development Framework (SSDF) | NIST; [csrc.nist.gov](https://csrc.nist.gov/pubs/sp/800/218/final) | Engineering baseline; supports the CRA and 18974 tracks | Secure development practices | [#19098](https://github.com/mrveiss/AutoBot-AI/issues/19098), [#19099](https://github.com/mrveiss/AutoBot-AI/issues/19099) |
| SLSA v1.2 (Supply-chain Levels for Software Artifacts) | OpenSSF; [slsa.dev](https://slsa.dev/spec/v1.2/) | Engineering baseline | Build provenance; reproducible, digest-pinned images | [#19098](https://github.com/mrveiss/AutoBot-AI/issues/19098), [#19099](https://github.com/mrveiss/AutoBot-AI/issues/19099) |
| CSAF 2.0 (Common Security Advisory Framework) | OASIS; [docs.oasis-open.org](https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html) | Engineering baseline; supports 18974 | Vulnerability advisories per release | [#19101](https://github.com/mrveiss/AutoBot-AI/issues/19101) |
| OpenVEX | OpenVEX project; [github.com/openvex/spec](https://github.com/openvex/spec) | Engineering baseline; supports 18974 | Exploitability statements next to the SBOM | [#19101](https://github.com/mrveiss/AutoBot-AI/issues/19101) |
| OpenSSF Scorecard; OpenSSF Best Practices badge | OpenSSF; [scorecard.dev](https://scorecard.dev/), [bestpractices.dev](https://www.bestpractices.dev/) | Engineering baseline | Repository security posture | — |
| WCAG 2.2 (Web Content Accessibility Guidelines), level AA | W3C; [w3.org/TR/WCAG22](https://www.w3.org/TR/WCAG22/) | Engineering baseline; supports 25010 | Accessibility of the web interfaces | [#19105](https://github.com/mrveiss/AutoBot-AI/issues/19105) |
| ETSI EN 301 549 V3.2.1 (2021-03), accessibility requirements for ICT products and services (ETSI also publishes V4.1.1, 2026-09; whether it is harmonised is not assessed here) | ETSI / CEN / CENELEC; [etsi.org](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/) | Engineering baseline; the EU counterpart of WCAG for procurement | Accessibility for public-sector and EU customers | [#19105](https://github.com/mrveiss/AutoBot-AI/issues/19105) |
| CIS Ubuntu Linux 22.04 LTS Benchmark (the OS the provisioning playbooks start from; benchmark version and profile recorded at review) | Center for Internet Security; [cisecurity.org](https://www.cisecurity.org/cis-benchmarks) | Engineering baseline | Hardening of deployed hosts | — |
| CIS Docker Benchmark (benchmark version and profile recorded at review) | Center for Internet Security; [cisecurity.org](https://www.cisecurity.org/cis-benchmarks) | Engineering baseline | Hardening of container hosts and images | — |
| CIS PostgreSQL 16 Benchmark (the `postgresql_version` the postgresql role defaults to; benchmark version and profile recorded at review). No CIS Redis benchmark is listed on the CIS benchmarks page, so none is named for the Redis Stack nodes | Center for Internet Security; [cisecurity.org](https://www.cisecurity.org/cis-benchmarks) | Engineering baseline | Hardening of database nodes | — |

## Assessed, adoption not decided

A readiness review exists for each of these, but **no programme exists for them**.
Nothing in AutoBot's documentation may describe the product as supporting, meeting or
being built for these until a row moves up to **Adopting** by owner decision.

| Target | Source | Basis |
|---|---|---|
| ISO/IEC 27001:2022, information security management systems | ISO/IEC JTC 1/SC 27, published by ISO | Readiness review, 2026-10-21 |
| ISO/IEC 27701:2025, privacy information management | ISO/IEC JTC 1/SC 27, published by ISO | Readiness review, 2026-10-21 |
| ISO/IEC 42001:2023, AI management systems | ISO/IEC JTC 1/SC 42, published by ISO | Readiness review, 2026-10-21 |
| ISO 22301:2019, business continuity management systems | ISO/TC 292, published by ISO | Readiness review, 2026-10-21 |
| ISO/IEC 27035 (multi-part series; the parts and editions each review covers are recorded in that review), information security incident management | ISO/IEC JTC 1/SC 27, published by ISO | Readiness review, 2026-10-21 |
| SOC 2 (Trust Services Criteria) | AICPA | Readiness review, 2026-10-21 |
| NIST AI RMF 1.0 (AI 100-1), with the Generative AI profile (NIST AI 600-1) | NIST; [nist.gov](https://www.nist.gov/itl/ai-risk-management-framework), [AI 600-1](https://doi.org/10.6028/NIST.AI.600-1) | Readiness review, 2026-10-21 |
| Data Act, Regulation (EU) 2023/2854 | European Parliament and Council; [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2023/2854/oj) | Readiness review, 2026-10-21 |
| HIPAA (conditional: only for deployments handling US health data) | US Department of Health and Human Services (hhs.gov) | Readiness review, 2026-10-21 |
| ISO 14001 (conditional: environmental management) | ISO/TC 207, published by ISO | Readiness review, 2026-10-21 |

## Changing this register

- **Every target has a Source and a Basis.** A target without both is not listed.
- **Moving a row to Adopting** needs an owner decision. Record its date in Basis and
  file an umbrella sub-issue.
- **A claim that a requirement is met** needs code or host evidence (file:line, test, CI
  run, or host observation) in the tracking issue. A readiness estimate is not evidence.
- **Wording anywhere else** in the repo says "working towards" or "designed to help
  with", never "compliant", "certified", "supports <standard>" or "built for <standard>".
