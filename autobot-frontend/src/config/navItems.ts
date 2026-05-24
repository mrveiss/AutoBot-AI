// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Navigation Items — Single Source of Truth
 *
 * Extracted from App.vue (#6499) so it can be unit-tested for coverage
 * against the router. Every top-level `requiresAuth: true` route in
 * `router/index.ts` MUST appear here unless it is in the test allowlist.
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
  adminOnly?: boolean;
}

// Data-driven navigation items: single source of truth for desktop + mobile nav
export const navItems: NavItem[] = [
  { to: '/home', labelKey: 'nav.home', icon: 'M10.707 2.293a1 1 0 00-1.414 0l-7 7v11a1 1 0 001 1h2a1 1 0 001-1v-5a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 001 1h2a1 1 0 001-1v-7l7-7a1 1 0 000-1.414z', iconRule: 'evenodd' },
  { to: '/chat', labelKey: 'nav.chat', icon: 'M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z', iconRule: 'evenodd' },
  // MVA-360: Live Canvas (behind VITE_FEATURE_CANVAS flag)
  { to: '/canvas', labelKey: 'nav.canvas', icon: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z', iconStroke: true },
  { to: '/knowledge', labelKey: 'nav.knowledge', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  { to: '/automation', labelKey: 'nav.automation', icon: 'M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z', iconRule: 'evenodd' },
  { to: '/analytics', labelKey: 'nav.analytics', iconPaths: ['M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z', 'M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z'] },
  // Issue #4703 / #6634: single Agents nav entry — Activity and Heartbeat
  // are reached as tabs inside the AgentsLayout shell, not as separate
  // sidebar items.
  { to: '/agents/registry', labelKey: 'nav.agentRegistry', icon: 'M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18', iconStroke: true },
  // Issue #929: Plugin Manager — marketplace integrated within /plugins
  { to: '/plugins', labelKey: 'nav.plugins', icon: 'M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z', iconStroke: true },
  { to: '/secrets', labelKey: 'nav.secrets', icon: 'M18 8a6 6 0 01-7.743 5.743L10 14l-1 1-1 1H6v2H2v-4l4.257-4.257A6 6 0 1118 8zm-6-4a1 1 0 100 2 2 2 0 012 2 1 1 0 102 0 4 4 0 00-4-4z', iconRule: 'evenodd' },
  // Issue #4270: Operations moved under /analytics/operations tab
  // Code Intelligence removed from main nav — merged into /analytics/codebase
  // Desktop nav removed — noVNC lives in the Chat tab. /desktop redirects to /chat.
  // Issue #902: Dev Tools moved into /analytics/dev-tools tab
  // Issue #4492: Custom Dashboard renamed to /home (removed separate nav entry)
  { to: '/preferences', labelKey: 'nav.preferences', icon: 'M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z', iconRule: 'evenodd' },
  // About moved to footer link
  // Issue #4465: Usage moved under /analytics/usage tab
  // Issue #1440: AutoResearch experiment dashboard (admin-only)
  { to: '/experiments', labelKey: 'nav.experiments', adminOnly: true, icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z' },
  // Issue #6590: Virtual LLM API keys admin view (admin-only)
  { to: '/admin/llm-keys', labelKey: 'nav.llmApiKeys', adminOnly: true, icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z', iconRule: 'evenodd' },
  // Issue #7773: Sandbox file inspector (admin-only)
  { to: '/admin/sandbox', labelKey: 'nav.adminSandbox', adminOnly: true, icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z', iconStroke: true },
  // Issue #7513: Host inventory management (admin-only)
  { to: '/admin/hosts', labelKey: 'nav.adminHosts', adminOnly: true, icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01', iconStroke: true },
  // GH#8250: LLC Company Portability — export + import
  { to: '/llc/portability', labelKey: 'nav.llcPortability', icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12', iconStroke: true },
];
