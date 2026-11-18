// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: Route guard for company-scoped LLC routes.
// Extracted from router/index.ts so the redirect logic is unit-testable.

import type { RouteLocationNormalized, RouteLocationRaw, RouteParams } from 'vue-router'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

/**
 * The company a route's params name: the first element of a repeated param, and '' when it is
 * missing, empty or the 'undefined'/'null' text a link built from an unset id produces. The one
 * definition shared by the guard (entering the company routes), the company layout (a
 * param-only change, which the guard does not see), the sidebar and the company context.
 */
export function companyIdFromParams(params?: RouteParams): string {
  const raw = params?.companyId
  const id = Array.isArray(raw) ? raw[0] : raw
  return !id || id === 'undefined' || id === 'null' ? '' : id
}

/**
 * `beforeEnter` guard for the `/llc/companies/:companyId/…` route group.
 *
 * - Missing/placeholder companyId → redirect to the company selector,
 *   carrying the intended destination so the selector can return there.
 * - Valid companyId → sync the Pinia store (covers deep links / bookmarks
 *   that bypass the selector) and allow navigation.
 */
export function llcCompanyParamGuard(
  to: RouteLocationNormalized,
): RouteLocationRaw | true {
  const companyId = companyIdFromParams(to.params)

  if (!companyId) {
    return { name: 'llc-company-select', query: { redirect: to.fullPath } }
  }

  useLlcCompanyStore().selectCompany(companyId)
  return true
}
