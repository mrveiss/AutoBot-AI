// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Legacy infrastructure paths that now live in the SLM console (#729, #20631).
 *
 * The SLM is admin only, so these are guarded routes, not bare redirects: a redirect record
 * resolves before any navigation guard and would send every user, including one whose user
 * store is not loaded yet, to the SLM. As admin routes they pass through the global guard in
 * router/index.ts, which loads the session first: a signed-out visitor goes to login and a
 * non-admin to /home. Only an admin reaches `beforeEnter`, which leaves for the SLM.
 *
 * The SLM uses web history (createWebHistory), so targets are plain paths, not `/#/` ones.
 * Wildcards go to the section root, not to the matching deep path: the SLM does have deep paths
 * (`/tools/terminal`, `/settings/admin/users`), but the old main-app sub-paths are not a one-to-one
 * map onto them, so only the section is a safe target.
 */
import type { RouteRecordRaw } from 'vue-router'
import { getSLMAdminUrl } from '@/config/ssot-config'

/** Renders nothing: `beforeEnter` always leaves before this would show. */
const EmptyView = { render: () => null }

/** Old main-app path -> SLM path; `deep` also covers `<path>/anything`. */
export const SLM_REDIRECTS: ReadonlyArray<{ path: string; slmPath: string; deep: boolean }> = [
  { path: '/tools', slmPath: '/tools', deep: true },
  { path: '/monitoring', slmPath: '/monitoring', deep: true },
  { path: '/settings', slmPath: '/settings', deep: true },
  { path: '/infrastructure', slmPath: '/infrastructure', deep: false },
  { path: '/tls-certificates', slmPath: '/security', deep: false },
]

/** Leave the SPA for the SLM; the global guard has already confirmed an admin. */
export function leaveForSlm(slmPath: string): false {
  window.location.href = `${getSLMAdminUrl()}${slmPath}`
  return false
}

function slmRoute(path: string, slmPath: string): RouteRecordRaw {
  return {
    path,
    component: EmptyView,
    meta: { requiresAuth: true, admin: true, hideInNav: true },
    beforeEnter: () => leaveForSlm(slmPath),
  }
}

export const slmRedirectRoutes: RouteRecordRaw[] = SLM_REDIRECTS.flatMap(
  ({ path, slmPath, deep }) => [
    slmRoute(path, slmPath),
    ...(deep ? [slmRoute(`${path}/:pathMatch(.*)*`, slmPath)] : []),
  ],
)
