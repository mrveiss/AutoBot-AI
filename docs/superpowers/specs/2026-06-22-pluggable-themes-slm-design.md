# Pluggable theme packages via /slm — design (#10472)

**Date:** 2026-06-22
**Issue:** #10472 (Phase 2 of #10461; Phase 1 shipped Ember as the user-GUI default in #10471)
**Status:** design — approved decisions captured below

## Goal

Let an operator **install new themes by uploading a theme folder/zip via /slm** (Service Lifecycle
Manager). Installed themes are delivered to the running **user frontend at runtime** (today themes
load only at build time) and become selectable by users in settings — without a rebuild/redeploy.

## Decisions (from brainstorming)

- **Reuse the plugin install infrastructure.** Themes are a backend-owned package type modeled on
  `autobot-backend/plugin_install.py` (zip-slip guard, symlink rejection, size/file-count caps,
  TOCTOU install lock, `__MACOSX` skip, id sanitisation). The /slm admin UI calls the backend
  theme API; the user frontend fetches the theme registry + CSS at runtime.
- **Strict CSS scoping + sanitisation.** Admin-only install. Uploaded CSS is untrusted: every
  selector must be scoped under `[data-theme-variant="<id>"]` or the install is rejected; external
  fetches are blocked. A theme physically cannot leak data or restyle outside its variant.
- **Runtime delivery via fetch + `adoptedStyleSheets`** (CSP-safe), not cross-origin `<link>` or
  inline `<style>`.

## Constraints

- Frontend and backend are **different origins** (frontend host vs `VITE_API_BASE_URL`).
- The frontend runs under a **strict CSP** (`style-src 'self'`, no `unsafe-inline`; #9966).
  → A cross-origin `<link rel=stylesheet>` or an inline `<style>` would both violate CSP. Fetching
  the CSS text via a CORS API call and adopting it as a constructed `CSSStyleSheet` does not.
- Built-in variants (`default`, `ember`) keep their build-time `@import` + no-flash bootstrap
  unchanged. This feature is purely additive.

## Architecture — three bounded units

### 1. Backend — theme package store + API (`autobot-backend`)

- `theme_install.py` — `install_from_zip(upload)` reusing the plugin hardening. Manifest
  `theme.json` = `{ id, name, author, version, supports: ["light","dark"] }`. `id` is sanitised and
  must match the variant id used in the CSS.
- Storage: `community-themes/<id>/` containing `theme.css` and optional `fonts/`, `icons/`.
  Atomic install: extract to a temp dir, validate, then move into place (mirrors plugins).
- `api/themes.py` (**admin** = the existing `autobot-backend` admin auth dependency used by other
  privileged endpoints, e.g. the plugin install routes — reused, not reinvented):
  - `POST /api/themes` — **admin**, multipart zip upload → install.
  - `DELETE /api/themes/{id}` — **admin**, uninstall (remove dir + registry entry).
  - `GET /api/themes` — registry metadata for any logged-in user (id, name, author, version,
    supports).
  - `GET /api/themes/{id}/theme.css` — serve the sanitised CSS.
  - `GET /api/themes/{id}/assets/*` — serve bundled fonts/icons from the theme dir (same-origin to
    the backend; path-traversal guarded).

### 2. Backend — CSS validator (`theme_css_validator.py`, pure / unit-testable)

Per the strict choice:
- Reject any selector **not** scoped under `[data-theme-variant="<id>"]` (manifest id).
- Block `@import`, external `url(http://…/https://…)`, `expression()`, `behavior:`, `javascript:` URLs.
- Allow `url(data:font/…)` and **relative** `url(./…)`/`url(fonts/…)` that resolve inside the theme
  dir only.
- Enforce size cap and rule-count cap. The variant id referenced in the CSS must equal the manifest
  `id`.
- Returns a structured result: ok, or the first offending rule/reason (surfaced in the 4xx).

### 3. Frontend — runtime theme registry + delivery

- `useThemeRegistry.ts` (new): on app init, `GET /api/themes` → list of installed theme descriptors.
- Extend `useThemeVariant.ts`: merge installed ids into `availableVariants` (+ labels/descriptions
  from the registry). The existing settings switcher (`EmberThemeToggle` in `PreferencesPanel`)
  lists them automatically — no UI rewrite.
- `applyThemeVariant(id)`: for an installed (non-built-in) id, lazily `fetch` its `theme.css`, build
  `new CSSStyleSheet().replace(text)`, push to `document.adoptedStyleSheets` once, then set
  `data-theme-variant="<id>"`. Built-in `default`/`ember` paths are unchanged.
- Admin theme-management view: a new `autobot-frontend` view in the operator/admin area, reachable
  under the `/slm` route group (this app already hosts `/slm/tools/novnc`) — upload (drag zip), list
  installed, uninstall. It is a thin client of the backend theme API and is gated to admins. The
  separate SLM control plane needs no changes; the theme store lives in `autobot-backend`.

## Data flow

admin uploads zip in /slm UI → `POST /api/themes` → validate + sanitise + extract + store →
registry updated. User frontend init → `GET /api/themes` → `availableVariants` extended → user
picks a theme → CSS fetched + adopted → `data-theme-variant` applied → tokens take effect (exactly
like `ember.css`).

## Error handling

- Bad zip / manifest / oversize / zip-slip / symlink → 4xx, nothing written (atomic temp-then-move).
- CSS failing scope/sanitise → whole install rejected with the offending rule.
- Non-admin → 403 on install/uninstall.
- Frontend registry fetch fails → fall back to built-in variants only (graceful).
- Stylesheet adopt/fetch fails → revert to the previous variant.

## No-flash caveat (explicit)

The pre-mount init script only knows **built-in** variants at build time, so the built-in default
(ember) stays flash-free. A **custom installed** theme set as a user's choice applies right after
the registry loads (a brief base-theme paint first). Acceptable for MVP; documented.

## Testing

- Validator unit tests: scoped-accept; unscoped-reject; `@import`/external-`url()` reject;
  `data:`/relative-`url()` accept; size/rule caps; id-mismatch reject.
- Install tests (reuse plugin test patterns): happy path; zip-slip; symlink; duplicate id; bad/missing
  manifest; oversize.
- API tests: admin gate (403 for non-admin); CRUD; serve CSS/assets; path-traversal guard.
- Frontend tests: registry merges into `availableVariants`; adopt-on-select; graceful fallback when
  registry/CSS fails.

## Out of scope (YAGNI)

Marketplace/discovery of themes; multi-node fleet distribution; theme versioning/upgrade UI;
per-user (non-admin) uploads; in-app theme editing.
