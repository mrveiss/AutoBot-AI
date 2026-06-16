<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# Code Duplication Elimination Report

**Branch:** `dedup-extraction` → `Dev_new_gui` · **Date:** 2026-06-10 · **Issue:** #9794

Behavior-preserving extraction sweep. Detector: `jscpd` (cpd 5.x),
`-k 70 -l 8 --skip-comments`, formats `python,typescript,javascript,vue`, tests
and generated/migration/mock/i18n paths excluded. Every code change keeps the
existing test suite green; no feature work was mixed in.

## Before / After

| Metric | Before | After | Δ |
|---|---|---|---|
| Duplication % | **1.1614%** | **1.0383%** | −0.123 pp |
| Duplicated lines | 16,783 | 14,983 | **−1,800** |
| Clones | 788 | 776 | −12 |

Net tracked-line change on the branch: **+303 / −2,232** across 25 files.

## Clusters acted on

### 1. `extensions/` → `middleware/` (largest cluster) — DONE · `2b64efd7b`
The `extensions` package was renamed to `middleware` (#7426) but the rename was
left half-finished: `__init__.py` and three `builtin/` modules were re-export
shims while `base.py`, `hooks.py`, `manager.py`, `hook_invoker.py`,
`extension_manifest.py` and `builtin/__init__.py` were full byte-identical copies
(only the `extensions.`→`middleware.` import prefix differed). jscpd's four
biggest backend clones (base 539, manager 388, hook_invoker 355, hooks 230).

- Moved `transcriber_extension.py` to canonical `middleware/builtin/` (it had been
  added only to the deprecated package via #9044); preserved the module-level
  `router` that `feature_routers.py` fetches via `getattr`.
- Converted the six leftover `extensions/` modules to thin re-export shims of
  `middleware`, matching the established #7426/#9779 shim style.
- Repointed prod transcriber wiring at the canonical module; fixed one test that
  patched the now-shimmed module's `logger` to patch the canonical one.

**Lines removed:** ~1,453 (−1,607 / +154). **Verification:** `extensions/` +
`middleware/` + transcriber tests = **120 passed**; import/identity parity check
green. Did **not** invent a new `autobot_shared/hooks/` framework (the prompt's
suggestion) — there is one real subsystem plus a backwards-compat alias; a third
abstraction would couple, not simplify.

### 3. Connector content-extraction helpers — DONE · `990d56fe2`
`gdrive.py` and `onedrive.py` carried byte-identical `_content_hash`,
`_extract_text_from_docx`, `_extract_text_from_pdf`; `_content_hash` was also
duplicated (functionally identical) in `nextcloud.py` and `gitlab.py`.

- New `knowledge/connectors/content_extraction.py` holds `content_hash`,
  `extract_text_from_docx`, `extract_text_from_pdf` (verbatim).
- Four connectors import them (aliased to the existing private names → call sites
  unchanged); dropped now-unused `hashlib`/`io` imports. OneDrive keeps its
  provider-specific xlsx/pptx extractors (genuine deltas).

**Lines removed:** ~60 net (5 files, −84 / +65, minus the new module).
**Verification:** gdrive + onedrive tests = **35 passed**; connector batch suite
**33 passed**; alias-identity smoke green.

### 5. `autobot-backend/static/` vite build artifacts — DONE · `2252e38ec`
Four hashed `static/js/index-*.js` bundles were tracked though `index.html`
references only one; the other three are stale builds (jscpd flagged 100+ line
clones between them). The existing `.gitignore` `static/js/` pattern is anchored
to the repo root and never matched the `autobot-backend/` subdir.

- Added `autobot-backend/static/{js,assets}/` ignore patterns and
  `git rm --cached` the 7 stale bundles (kept on disk; regenerated each deploy).
  `index.html`/`favicon.ico`/`error_messages.yaml` stay tracked (source).

**Lines removed from tracking:** 541.

## New shared modules created

| Module | Replaces |
|---|---|
| `autobot-backend/knowledge/connectors/content_extraction.py` | 3 duplicated helpers across 4 connectors |
| `autobot-backend/extensions/*.py` (now shims) | full copies of `middleware/*` |

## CI guard added — `e9370732c`

`.github/workflows/duplication-guard.yml` runs jscpd with the sweep's exact flags
and fails when duplication exceeds **1.05%** (post-cleanup baseline 1.04% + jitter
margin). Threshold gate, not zero-duplication — ratchet THRESHOLD down as future
cleanup PRs land. Uses `--threshold` (not bare `--exit-code`, which would fail on
any duplicate). No untrusted event data in run steps.

## Clusters deliberately skipped / deferred

### 2. `code_intelligence/security_analyzer.py` vs `security/` package — SKIPPED · filed #9856
The prompt's plan (make the package canonical, delete the monolith) is **impossible**:
- The `security/` package (#712 modularization) is **broken** — `constants.py:13`
  imports `DEBUG_MODE_VARS` from `autobot_shared.ssot_constants`, which no longer
  exists; the package raises `ImportError` on import.
- It is **unwired** (zero importers) and **untested** (no tests in `security/`).
- The monolith `security_analyzer.py` is the live, tested SSOT (4 importers; 39
  vulnerability types).

Completing or removing #712 is repair/feature work (fixing a broken import,
re-wiring 4 consumers, equivalence verification the deps-light env can't do — its
test stubs missing deps to `MagicMock`). Out of scope for behavior-preserving
extraction; deleting it would violate the "never delete unwired work" rule.
**Filed #9856** with both resolution paths.

### 4. Vue frontend (largest overall source) — DEFERRED · filed umbrella #9859
**9,666 duplicated lines across 274 component pairs** — css 7,649, html 1,335,
ts 682. The named offenders (analytics dashboards, knowledge modals, plugin
modals) are all scoped-CSS / template clones. Deferred because:
- No offender has unit tests and there is no visual-regression harness wired for
  them, so **visual identity cannot be evidenced in a headless environment** — and
  "visual output must be identical" was the hard requirement.
- No clone pair has a wholesale-identical `<style>` block; every pair is a partial
  overlap, so CSS extraction is **cascade-order sensitive** (silent visual drift).
- `BaseModal.vue`, the `base/` component library and `design-system/tokens.ts`
  already exist — this is a migration + visual-QA campaign, not greenfield.

**Filed #9859** with the safe incremental methodology (stand up visual regression
first; extract identical scoped CSS via `<style scoped src>`; migrate modal chrome
onto `BaseModal`; one PR per component family). The small `<script>`/`.ts` pairs
(≤50 L: `FeatureFlagsApiClient`↔`VisionMultimodalApiClient`, llc board views, …)
were left alone — extracting a shared base for them would couple unrelated domains
for marginal gain.

### Other backend clusters left as-is (documented, not filed)
- **`gdrive`/`onedrive` `_classify_change` + OAuth `_request`** (identical bodies)
  depend on per-connector `_load_ts`/`_store_ts` that **differ**, so hoisting them
  to the base would risk behavior change. Duplication is cheaper than the wrong
  abstraction here.
- **`code_analysis/auto-tools/security_deep_sanitizer.py` ↔ `security_sanitizer.py`**
  (131 L) and **`api/analytics_precommit.py` ↔ `code_intelligence/precommit_analyzer.py`**
  (111 L) — overlap spans different layers (API vs analyzer; two sanitizer tiers);
  consolidating would couple an HTTP surface to an analysis engine. Left as-is.

## Methodology note

Each acted-on cluster was verified by running the relevant existing test suite to
green after the change; skips were taken whenever extraction required unverifiable
behavior/visual guarantees, broken/unwired code, or coupling of unrelated domains.
