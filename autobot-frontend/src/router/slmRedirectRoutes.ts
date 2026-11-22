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
import { BATCH_JOBS_PATH, VISION_PATH } from './userToolRoutes'

/** Renders nothing: `beforeEnter` always leaves before this would show. */
const EmptyView = { render: () => null }

/** Old main-app path -> SLM path; `deep` also covers `<path>/anything`. */
export const SLM_REDIRECTS: ReadonlyArray<{ path: string; slmPath: string; deep: boolean }> = [
  { path: '/tools', slmPath: '/tools', deep: true },
  { path: '/monitoring', slmPath: '/monitoring', deep: true },
  { path: '/settings', slmPath: '/settings', deep: true },
  { path: '/infrastructure', slmPath: '/infrastructure', deep: false },
  { path: '/tls-certificates', slmPath: '/security', deep: false },
  // #20605: remote desktop and the theme manager are SLM screens; old bookmarks follow them.
  { path: '/slm/tools/novnc', slmPath: '/tools/novnc', deep: false },
  { path: '/slm/themes', slmPath: '/settings/admin/themes', deep: false },
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

/**
 * #20644: Batch Processing and Vision went the other way, from the SLM to this app. Their old
 * `/tools/*` paths stay here instead of following the `/tools` wildcard to the SLM. A static path
 * outranks the `/tools/:pathMatch(.*)*` wildcard, and these come first in the list as well.
 */
export const MOVED_FROM_SLM: ReadonlyArray<{ path: string; to: string }> = [
  { path: '/tools/batch', to: BATCH_JOBS_PATH },
  { path: '/tools/vision', to: VISION_PATH },
]

export const slmRedirectRoutes: RouteRecordRaw[] = [
  ...MOVED_FROM_SLM.map(({ path, to }): RouteRecordRaw => ({ path, redirect: to })),
  ...SLM_REDIRECTS.flatMap(({ path, slmPath, deep }) => [
    slmRoute(path, slmPath),
    ...(deep ? [slmRoute(`${path}/:pathMatch(.*)*`, slmPath)] : []),
  ]),
]
