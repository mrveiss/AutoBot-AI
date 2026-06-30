// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * orgContext — resolves the currently-selected LLC company id so it can be
 * attached as the `X-Organization-Id` header on every backend request.
 *
 * Org-scoped Company OS endpoints resolve tenant context from this header;
 * without it they reject with 400 "Organization context required" (#10750 A5).
 *
 * Resolution order (single source of truth = the llcCompany Pinia store):
 *   1. live Pinia store  — `useLlcCompanyStore().selectedCompanyId`
 *   2. persisted value   — localStorage key written by the store's
 *      pinia-plugin-persistedstate config (`pick: ['selectedCompanyId']`)
 *
 * The store cannot be imported at the ApiClient/fetchWithAuth layer (the store
 * imports ApiClient → circular), so when Pinia is not yet active we read the
 * persisted selection directly. Both paths return the SAME value.
 */

import { getActivePinia } from 'pinia'

// Must match the `persist.key` in useLlcCompanyStore.ts.
const LLC_COMPANY_STORAGE_KEY = 'autobot-llc-company'

/** Read the persisted selection written by pinia-plugin-persistedstate. */
function readPersistedCompanyId(): string {
  try {
    if (typeof localStorage === 'undefined') return ''
    const stored = localStorage.getItem(LLC_COMPANY_STORAGE_KEY)
    if (!stored) return ''
    const parsed: { selectedCompanyId?: unknown } = JSON.parse(stored)
    return typeof parsed.selectedCompanyId === 'string' ? parsed.selectedCompanyId : ''
  } catch {
    return ''
  }
}

/**
 * Returns the selected company id, or '' when none is selected / unavailable
 * (SSR, no Pinia, no persisted value). Prefers the live store; falls back to
 * the persisted localStorage value so it works at the low-level request layer.
 */
export function getSelectedCompanyId(): string {
  try {
    const pinia = getActivePinia()
    if (pinia) {
      // Defer import to call time so this module has no static dependency on
      // the store (which imports ApiClient — would be circular at the header
      // injection sites). require-style dynamic access keeps it synchronous.
      const stores = (pinia as unknown as {
        _s?: Map<string, { selectedCompanyId?: unknown }>
      })._s
      const store = stores?.get('llcCompany')
      if (store && typeof store.selectedCompanyId === 'string') {
        return store.selectedCompanyId
      }
    }
  } catch {
    // fall through to persisted value
  }
  return readPersistedCompanyId()
}

/**
 * Mutates the given Headers object to include `X-Organization-Id` when a
 * company is selected. No-op (header omitted) when none is selected so non-LLC
 * requests and unauthenticated flows are unaffected. Does not overwrite a
 * header the caller already set.
 */
export function applyOrgHeader(headers: Headers): void {
  if (headers.has('X-Organization-Id')) return
  const companyId = getSelectedCompanyId()
  if (companyId) {
    headers.set('X-Organization-Id', companyId)
  }
}
