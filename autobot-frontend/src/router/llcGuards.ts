// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: Route guard for company-scoped LLC routes.
// Extracted from router/index.ts so the redirect logic is unit-testable.

import type { RouteLocationNormalized, RouteLocationRaw } from 'vue-router'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

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
  const raw = to.params.companyId
  const companyId = Array.isArray(raw) ? raw[0] : raw

  if (!companyId || companyId === 'undefined' || companyId === 'null') {
    return { name: 'llc-company-select', query: { redirect: to.fullPath } }
  }

  useLlcCompanyStore().selectCompany(companyId)
  return true
}
