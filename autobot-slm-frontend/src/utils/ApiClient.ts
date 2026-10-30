// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Canonical SLM API Client (#12420, #14908).
 *
 * The transport (timeout/abort, GET retry with backoff and Retry-After, query params,
 * HttpError, JSON/text parsing, uploads) is the kit's `ApiClientBase`. This subclass is only
 * what is SLM's own:
 *
 *  - Base URL from `getSlmApiBase()` (ssot-config) -- '/api' standalone or '/slm/api'
 *    co-located. Endpoints are relative to that base (`get('/nodes')` -> `/api/nodes`).
 *  - Auth token read through `utils/authStorage` (sessionStorage, then the legacy
 *    localStorage copy) -- the same reader `stores/auth.ts` uses.
 *  - 401 policy: clear the SLM session and redirect to the base-aware login (#18892), but only
 *    when the request carried a bearer token and did not target an auth/mfa endpoint. A client
 *    for the main backend sets `setKeepSessionOn401(true)` so its 401 surfaces and never logs
 *    out (#10193, #19819).
 *  - 503 is "could not decide" (#18892): the session is kept and GET retries it.
 *  - `getContract`, typed by the generated contract (#16292).
 */

import { createLogger } from '@/utils/debugUtils'
import { getSlmApiBase } from '@/config/ssot-config'
import { clearSlmSession, readSlmToken } from '@/utils/authStorage'
import { buildLoginUrl, isLoginPathname } from '@/utils/loginRedirect'
import {
  ApiClientBase,
  SERVICE_UNAVAILABLE_STATUS,
  parseRetryAfterMs,
  withQuery,
  type GetPath,
  type GetResponse,
  type TransportRequestOptions,
} from '@autobot/ui'
import type { paths } from '@/types/generated/api'

const logger = createLogger('SlmApiClient')

// Kept importable from here: they moved into the kit with the transport.
export { SERVICE_UNAVAILABLE_STATUS, parseRetryAfterMs, withQuery }

// Default request timeout. Module-level constant sourced from an env var so it
// is never hard-coded at a call site (falls back to 30s when unset).
const DEFAULT_TIMEOUT_MS = (() => {
  const raw = import.meta.env.VITE_SLM_API_TIMEOUT_MS
  const parsed = raw != null && raw !== '' ? parseInt(String(raw), 10) : NaN
  return Number.isNaN(parsed) ? 30_000 : parsed
})()

export type RequestOptions = TransportRequestOptions

/** GET only: `'text'` returns the body as a string instead of parsing JSON (#12363). */
export interface GetOptions extends RequestOptions {
  responseType?: 'json' | 'text'
}

export class SlmApiClient extends ApiClientBase<RequestOptions> {
  // Optional host/base override (defaults to getSlmApiBase() when unset).
  private baseUrlOverride: string | null = null

  constructor() {
    super(DEFAULT_TIMEOUT_MS, logger)
  }

  // Public setter for base URL (used by plugin configuration / tests).
  setBaseUrl(url: string): void {
    this.baseUrlOverride = url
  }

  getConfiguration(): Record<string, unknown> {
    return { baseUrl: this.resolveBaseUrl(), timeout: this.defaultTimeout }
  }

  protected resolveBaseUrl(): string {
    return this.baseUrlOverride ?? getSlmApiBase()
  }

  // The one SLM token reader (utils/authStorage, #17856 row 8).
  protected getAuthToken(): string | null {
    return readSlmToken()
  }

  // Auth/MFA endpoints must never trigger a session-clearing 401 handler -- a 401
  // there is a credential failure, not a rejected session.
  protected isAuthEndpoint(endpoint: string): boolean {
    return endpoint.includes('/auth/') || endpoint.includes('/mfa/')
  }

  // Only destructive when the request carried a bearer token: a 401 on a
  // token-less background call is not a session rejection.
  protected handleUnauthorized(endpoint: string, tokenWasAttached: boolean): void {
    if (!tokenWasAttached) {
      logger.debug('401 on token-less request — not clearing session (no session to invalidate):', endpoint)
      return
    }
    logger.warn('401 Unauthorized, clearing SLM session:', endpoint)
    clearSlmSession()
    if (typeof window !== 'undefined' && !isLoginPathname(window.location.pathname)) {
      window.location.href = buildLoginUrl(window.location)
    }
  }

  // 503 is "could not decide": never clear the session or redirect. The error surfaces to
  // the caller, and GET retries it with backoff (only 4xx are non-retryable).
  protected onResponse(response: Response, endpoint: string): void {
    if (response.status === SERVICE_UNAVAILABLE_STATUS) {
      logger.warn('503 Service Unavailable, keeping SLM session (retryable):', endpoint)
    }
  }

  // The upload goes through XHR, which has no shared header path: attach the bearer here.
  protected authorizeUpload(xhr: XMLHttpRequest): void {
    const token = this.getAuthToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
  }

  // GET typed by the generated contract (#16292). The path must be a GET in `paths`, and the
  // response type comes from its 200 schema. Contract keys carry the `/api` prefix; the
  // client's base already supplies it (or `/slm/api`).
  async getContract<P extends GetPath<paths>>(
    path: P,
    options: RequestOptions = {}
  ): Promise<GetResponse<paths, P>> {
    return (await this.get(path.replace(/^\/api(?=\/)/, ''), options)) as GetResponse<paths, P>
  }
}

// Singleton -- the canonical SLM API client. Construction is side-effect free
// (base URL is resolved lazily per request), so eager instantiation is safe.
export const slmApiClient = new SlmApiClient()

export default slmApiClient
