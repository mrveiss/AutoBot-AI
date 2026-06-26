// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Navigation Items — Single Source of Truth
 *
 * Extracted from App.vue (#6499) so it can be unit-tested for coverage
 * against the router. Every top-level `requiresAuth: true` route in
 * `router/index.ts` MUST appear here unless it carries `hideInNav: true`
 * on its route meta or is in the test allowlist.
 *
 * GH#8748: consolidated from 17+ items to ≤7 primary items (Miller's Law).
 * Secondary items moved to profileMenuItems / adminMenuItems and surfaced
 * from the profile dropdown rather than the primary nav rail.
 *
 * @see src/__tests__/nav-items-coverage.test.ts
 */

// iconRule is typed as a literal union to satisfy SVG fill-rule / clip-rule prop types (#4699)
export type SvgFillRule = 'evenodd' | 'nonzero' | 'inherit';

export interface NavItem {
  to: string;
  labelKey: string;
  icon?: string;
  iconPaths?: string[];
  iconRule?: SvgFillRule;
  iconStroke?: boolean;
  /**
   * Gate this item behind `VITE_FEATURE_<featureFlag.toUpperCase()>`.
   * The flag is a UX visibility toggle only — never a security boundary
   * (route/API access is enforced server-side via RBAC). Explicit
   * `'true'` shows, explicit `'false'` hides; when the env var is unset the
   * item falls back to `featureDefaultVisible` (see below).
   */
  featureFlag?: string;
  /**
   * Visibility when the feature flag's env var is UNSET (fail-safe default).
   * Shipped features should set `true` (fail-open — stay visible even if the
   * flag never reaches the build); experimental/preview features omit it so
   * they fail closed (hidden until explicitly enabled). Default: `false`.
   */
  featureDefaultVisible?: boolean;
}

/**
 * Returns items whose featureFlag (if any) resolves to visible in the given
 * env object. Resolution per item: no flag → always visible; flag `'true'` →
 * visible; flag `'false'` → hidden; flag unset → `featureDefaultVisible`
 * (fail-safe, default hidden). Pass `import.meta.env` in production; pass a
 * plain object in tests.
 */
export function filterByFeatureFlag(
  items: NavItem[],
  env: Record<string, string | boolean | undefined> = import.meta.env,
): NavItem[] {
  return items.filter((item) => {
    if (!item.featureFlag) return true;
    const value = env[`VITE_FEATURE_${item.featureFlag.toUpperCase()}`];
    if (value === 'true') return true;
    if (value === 'false') return false;
    return item.featureDefaultVisible ?? false;
  });
}

// ─── Primary nav (≤7 items for non-admin users at 1440 px) ───────────────────
// Data-driven navigation items: single source of truth for desktop + mobile nav
export const navItems: NavItem[] = [
  { to: '/home', labelKey: 'nav.home', icon: 'M10.707 2.293a1 1 0 00-1.414 0l-7 7v11a1 1 0 001 1h2a1 1 0 001-1v-5a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 001 1h2a1 1 0 001-1v-7l7-7a1 1 0 000-1.414z', iconRule: 'evenodd' },
  { to: '/chat', labelKey: 'nav.chat', icon: 'M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z', iconRule: 'evenodd' },
  // GH#8757: AI Documents and the Transcriber moved into the Knowledge sidebar
  // (BROWSE group) — see KnowledgeView.vue. Routes live under /knowledge/* now;
  // legacy /documents and /transcriber paths redirect there (router/index.ts).
  { to: '/knowledge', labelKey: 'nav.knowledge', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  { to: '/automation', labelKey: 'nav.automation', icon: 'M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z', iconRule: 'evenodd' },
  { to: '/analytics', labelKey: 'nav.analytics', iconPaths: ['M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z', 'M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z'] },
  // Agents nav entry removed (TASK 1c): /agents/registry duplicates SLM Admin's
  // /slm/agents/local-agents. Route is kept in router/index.ts for deep links.
  // GH#8748: LLC views consolidated to one "Company OS" entry (was 5 separate items)
  // GH#9627: entry point is the company selector; LLC sub-views are reached
  // via the contextual LLC sidebar once a company is selected.
  { to: '/llc/select-company', labelKey: 'nav.companyOs', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4', iconStroke: true },
  // Issue #9890: Vision Automation is reachable via Workflow Builder sidebar + direct route.
  // It is NOT in the primary nav rail. To gate a future entry, add a `featureFlag`
  // (and `featureDefaultVisible: true` only if it should ship visible by default).
  // #9984 re-wired filterByFeatureFlag into both desktop and mobile nav in App.vue.
];

// ─── Profile/settings menu items (GH#8748) ───────────────────────────────────
// Shown in the profile dropdown — not in the primary nav rail.
// Routes must carry hideInNav: true in router/index.ts.
export const profileMenuItems: NavItem[] = [
  // MVA-360: Live Canvas — experimental, gated by VITE_FEATURE_CANVAS (GH#8758).
  // Fails CLOSED (hidden) unless the env var is explicitly 'true'.
  { to: '/canvas', labelKey: 'nav.canvas', icon: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z', iconStroke: true, featureFlag: 'canvas' },
  // Issue #929: Plugin Manager
  { to: '/plugins', labelKey: 'nav.plugins', icon: 'M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z', iconStroke: true },
  { to: '/secrets', labelKey: 'nav.secrets', icon: 'M18 8a6 6 0 01-7.743 5.743L10 14l-1 1-1 1H6v2H2v-4l4.257-4.257A6 6 0 1118 8zm-6-4a1 1 0 100 2 2 2 0 012 2 1 1 0 102 0 4 4 0 00-4-4z', iconRule: 'evenodd' },
  { to: '/preferences', labelKey: 'nav.preferences', icon: 'M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z', iconRule: 'evenodd' },
];

// ─── Admin-only menu items (GH#8748) ─────────────────────────────────────────
// Shown in an "Admin" section of the profile dropdown — not in the primary nav.
// Routes must carry hideInNav: true in router/index.ts.
export const adminMenuItems: NavItem[] = [
  // Issue #1440: AutoResearch experiment dashboard
  { to: '/experiments', labelKey: 'nav.experiments', icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z' },
  // MVA-2999: LLM provider fallback status (added here via GH#9627 — route was
  // missing both hideInNav and a menu entry, failing nav-items-coverage)
  { to: '/admin/llm-providers', labelKey: 'nav.llmProviders', icon: 'M13 10V3L4 14h7v7l9-11h-7z', iconStroke: true },
  // Issue #6590: Virtual LLM API keys admin view
  { to: '/admin/llm-keys', labelKey: 'nav.llmApiKeys', icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z', iconRule: 'evenodd' },
  // Issue #7773: Sandbox file inspector
  { to: '/admin/sandbox', labelKey: 'nav.adminSandbox', icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z', iconStroke: true },
  // Issue #7513: Host inventory management
  { to: '/admin/hosts', labelKey: 'nav.adminHosts', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01', iconStroke: true },
  // GH#6470: Budget policy management
  { to: '/admin/budget-policies', labelKey: 'nav.budgetPolicies', icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z', iconStroke: true },
  // GH#8996: Admin view of all active shared chat links
  { to: '/admin/shared-links', labelKey: 'nav.sharedLinks', icon: 'M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 01-5.656-5.656l1.5-1.5m6.328-1.328a4 4 0 010-5.656l3-3a4 4 0 015.656 5.656l-1.5 1.5', iconStroke: true },
];
