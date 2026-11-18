// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21512: where the company switch in the Company OS sidebar lands.

import type { RouteLocationNormalizedLoaded, RouteLocationRaw } from 'vue-router'

type SwitchSource = Pick<RouteLocationNormalizedLoaded, 'name' | 'params'>

/** A route param that names a record owned by the company in the URL: `boardId`, `portfolioId`, ... */
const isOwnedRecordParam = (name: string): boolean => name !== 'companyId' && name.endsWith('Id')

/**
 * The location to push when the sidebar switches the company shown to `id`.
 *
 * The same view in the new company is the target, except where the URL carries the id of a record the
 * OLD company owns, which the new company answers with "not found":
 * - a board (`:boardId`) falls back to the new company's backlog;
 * - any other owned id (`:portfolioId`, `:programId`, ...) falls back to its portfolios, the root of
 *   that hierarchy.
 * Every other param is kept. `:section` of the automation module is a view selector, not an id the
 * company owns, so it stays and the switch lands on the same section.
 */
export function companySwitchTarget(route: SwitchSource, id: string): RouteLocationRaw {
  if (route.params.boardId) {
    return { name: 'llc-backlog', params: { companyId: id } }
  }
  if (Object.keys(route.params).some(isOwnedRecordParam)) {
    return { name: 'llc-portfolios', params: { companyId: id } }
  }
  // Every company-scoped route is named (the one unnamed record is a redirect that never stays current).
  return { name: route.name as NonNullable<typeof route.name>, params: { ...route.params, companyId: id } }
}
