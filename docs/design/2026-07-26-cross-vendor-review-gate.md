---
tags: [type/architecture, status/proposed, component/backend, component/llc]
date: 2026-07-26
issue: 12618
umbrella: 12617
---

# Cross-Vendor Second-Opinion Review Gate

## Overview

LLC review gates currently verify work with the **same** provider that produced it. This design adds an optional **second-opinion verifier tier** that requires an *independent* LLM provider to sign off before a gate resolves, so a single model's systematic blind spots cannot pass through unchallenged.

**Scope:** review-gate policy + findings verifier only. No new provider transport — it reuses the existing multi-provider `LLMService` and provider-agnostic tier resolution.

## Problem

- `llc/services/review_gate.py` + `llc/models/review_gate.py` — gates are **human** (`requires_human_review`, `reviewer_role`); there is no automated cross-model check.
- `llc/services/findings_verify.py` — the false-positive verifier calls `get_llm_service()` (the single default `LLMService` singleton). The checker shares the author's provider/model family, so correlated errors (confident-but-wrong findings, consistently-misjudged real bugs) survive the gate.
- `llc/services/model_tiers.py` — already provider-agnostic and can identify a provider, but nothing requires the verifier to differ from the author.

## Goals / Non-Goals

**Goals**
- A verifier tier that runs on a provider distinct from the author when ≥2 providers are configured.
- Per-company, per-item-type policy control, defaulting **off**.
- Preserve the current **fail-closed** verifier semantics.
- Graceful, non-fatal degradation on single-provider installs.

**Non-Goals**
- Replacing the human review gate (cross-vendor disagreement escalates *to* it).
- Adding a new LLM provider or SDK.
- Changing the findings data model.

## Architecture

```
Finding produced (author provider = P_a)
            │
            ▼
   ReviewGatePolicyService.get(company, item_type)
            │  requires_cross_vendor_review?
      ┌─────┴─────┐
      │ false     │ true
      ▼           ▼
 same-vendor   resolve verifier provider P_v != P_a
 verifier      (via model_tiers / LLMService registry)
 (current)          │
                    ▼
             run verifier on P_v  ── fail ──► Verdict(is_real=False, conf=0.0)   [fail-closed]
                    │
                    ▼
          combine(author_verdict, P_v_verdict)
            ├─ agree      ─► gate resolves automatically
            └─ disagree   ─► escalate to human review gate
```

### Provider selection
`select_verifier_provider(author_provider)` asks the `LLMService` registry for configured providers, excludes `author_provider`, and picks by the existing tier preference in `model_tiers.py`. If the exclusion leaves an empty set → degrade (see below).

### Verdict combination
- **Agree** (both `is_real` equal): resolve automatically with the higher-confidence rationale attached.
- **Disagree**: do **not** auto-pass. Route to the existing human review gate (`requires_human_review=True` for this item), recording both verdicts as decision context so the human sees the split.

## Policy model

Extend `LLMReviewGatePolicy` (`llc/models/review_gate.py`) with `requires_cross_vendor_review: bool` (default `False`). `ReviewGatePolicyService.install_defaults` seeds it off for every item type. Exposed/editable via `llc/api/review_gate_policies.py` per company + item type.

## Graceful degradation

If `cross_vendor` is requested but the registry yields no provider ≠ author:
1. Log a single `warning` (not per-call spam).
2. Fall back to the current same-vendor verifier.
3. Never hard-fail — a single-provider deploy behaves exactly as today.

This keeps the feature config-gated and safe for installs with one provider.

## Failure modes

| Condition | Behavior |
|-----------|----------|
| Verifier provider call errors/times out | `Verdict(is_real=False, confidence=0.0, rationale="unverifiable: …")` (fail-closed, unchanged) |
| Only one provider configured | Warn once → same-vendor verifier |
| Author provider unresolvable | Treat as "no exclusion possible" → degrade |
| Both verdicts low-confidence | Escalate to human gate |

## Files affected

- `autobot-backend/llc/services/findings_verify.py` — add `cross_vendor` mode + `select_verifier_provider` + verdict combination.
- `autobot-backend/llc/models/review_gate.py` — add `requires_cross_vendor_review` column.
- `autobot-backend/llc/services/review_gate.py` — honor the flag; seed default off.
- `autobot-backend/llc/api/review_gate_policies.py` — expose the flag.
- `autobot-backend/llc/services/model_tiers.py` — read-only reuse for provider identity/selection.
- Migration: add nullable-with-default column to the review-gate policy table (no data loss).

## Testing

- Provider selection excludes author provider when ≥2 configured.
- Verdict combination: agree → auto-resolve; disagree → human gate with both verdicts recorded.
- Degradation: single-provider deploy warns once and uses same-vendor verifier; no exception.
- Fail-closed preserved on verifier error.

## Rollout

Ship off by default. Enable per company/item-type (e.g. `bug` items) once a second provider is configured. No behavior change for existing installs until the flag is set.

## Model Used

Opus 4.8 (1M context)
