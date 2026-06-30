// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * fetchWithAuth — drop-in replacement for fetch() that injects the JWT
 * Authorization header from localStorage.
 *
 * Reads the same key as ApiClient._getAuthToken() so auth state is consistent.
 * Use this for any raw fetch() call that needs to reach an authenticated backend
 * endpoint.  ApiClient.rawRequest() is preferred for new code; this helper
 * exists to fix existing raw fetch() call-sites without a full refactor.
 *
 * Issue #979: JWT token not attached to backend API requests.
 * Issue #10750 (A5): also attach the selected company as X-Organization-Id so
 * org-scoped Company OS endpoints resolve tenant context.
 */

import { applyOrgHeader } from '@/utils/orgContext'

export function getAuthToken(): string | null {
  try {
    const stored = localStorage.getItem('autobot_auth')
    if (!stored) return null
    const auth: { token?: string } = JSON.parse(stored)
    if (auth.token && auth.token !== 'single_user_mode') {
      return auth.token
    }
    return null
  } catch {
    return null
  }
}

/**
 * Wraps native fetch() with Bearer-token injection and the X-Organization-Id
 * header for the selected company. If no valid token is found the request still
 * proceeds (matches pre-existing behaviour; let the server decide), and the org
 * header is omitted when no company is selected.
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAuthToken()

  // Build a new Headers object so we don't mutate the caller's options.
  const headers = new Headers(options.headers)
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  // Attach the selected company id as org context (#10750 A5); no-op when none.
  applyOrgHeader(headers)

  return fetch(url, { ...options, headers })
}
