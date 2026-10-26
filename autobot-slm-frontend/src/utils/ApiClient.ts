// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Canonical SLM API Client (#12420 Phase 1).
 *
 * A single fetch-based HTTP client for the SLM Admin frontend, mirroring the
 * canonical `autobot-frontend/src/utils/ApiClient.ts` and adapting it to SLM:
 *
 *  - Base URL resolved from `getSlmApiBase()` (ssot-config) — '/api' standalone
 *    or '/slm/api' when co-located. Endpoints are passed relative to that base
 *    (e.g. `get('/nodes')` → `/api/nodes`), matching the existing SLM axios
 *    composable convention so Phase 2 call sites drop only the base prefix.
 *  - Auth token read through `utils/authStorage` (sessionStorage, then the
 *    legacy localStorage copy) -- the same reader `stores/auth.ts` uses.
 *  - 401 handling matches SLM's convention: clear the session keys and redirect
 *    to the base-aware login (`<BASE_URL>login?redirect=...`, #18892), but only when the request
 *    actually carried a bearer token and did not target an auth/mfa endpoint.
 *  - Timeout via AbortController, exponential-backoff retry on GET, FormData
 *    passthrough, `rawRequest` for streaming/blob access, and 204 handling.
 *
 * Per the #12420 plan this is a COPY-ADAPT (separate per-app client); a shared
 * core is a later ADR. Nothing imports this yet — Phase 2 migrates the ~71
 * `getSlmApiBase()` call sites and ~48 fetch/axios files onto it.
 */

import { createLogger } from '@/utils/debugUtils'
import { getSlmApiBase } from '@/config/ssot-config'
import { clearSlmSession, readSlmToken } from '@/utils/authStorage'
import { buildLoginUrl, isLoginPathname } from '@/utils/loginRedirect'
import { backoffDelay, httpErrorFrom, isHttpClientError, parseJsonBody, RETRY_BACKOFF, type GetPath, type GetResponse } from '@autobot/ui'
import type { paths } from '@/types/generated/api'

const logger = createLogger('SlmApiClient')

// HTTP status for "revocation check unavailable" (#18892). The session is NOT
// rejected -- the server could not decide -- so the client keeps it and retries.
export const SERVICE_UNAVAILABLE_STATUS = 503

// Parse a Retry-After header (delta-seconds or HTTP-date) into milliseconds.
// Missing, negative or unparseable values yield 0, i.e. plain backoff.
export function parseRetryAfterMs(header: string | null, now: number = Date.now()): number {
  if (!header) return 0
  const value = header.trim()
  if (/^\d+$/.test(value)) return Number(value) * 1000
  const at = Date.parse(value)
  return Number.isNaN(at) ? 0 : Math.max(0, at - now)
}

// Default request timeout. Module-level constant sourced from an env var so it
// is never hard-coded at a call site (falls back to 30s when unset).
const DEFAULT_TIMEOUT_MS = (() => {
  const raw = import.meta.env.VITE_SLM_API_TIMEOUT_MS
  const parsed = raw != null && raw !== '' ? parseInt(String(raw), 10) : NaN
  return Number.isNaN(parsed) ? 30_000 : parsed
})()

export interface RequestOptions {
  headers?: Record<string, string>
  timeout?: number
  maxRetries?: number
  signal?: AbortSignal
  /**
   * When true, the client does not emit a WARN log on final failure. Use for
   * endpoints whose absence/timeout is handled gracefully by the caller
   * (optional widgets, health probes) so they don't generate console noise.
   */
  suppressErrorLog?: boolean
  /**
   * Query parameters, appended URL-encoded to the endpoint (#12363). `null` and
   * `undefined` values are left out, so an optional filter needs no branching.
   */
  params?: Record<string, string | number | boolean | null | undefined>
}

/** GET only: `'text'` returns the body as a string instead of parsing JSON (#12363). */
export interface GetOptions extends RequestOptions {
  responseType?: 'json' | 'text'
}

/** Append `params` to `endpoint`, skipping null/undefined; keeps an existing `?query`. Scalars only (no arrays). */
export function withQuery(endpoint: string, params: RequestOptions['params']): string {
  if (!params) return endpoint
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) query.append(key, String(value))
  }
  const text = query.toString()
  if (!text) return endpoint
  return `${endpoint}${endpoint.includes('?') ? '&' : '?'}${text}`
}

export class SlmApiClient {
  // Optional host/base override (defaults to getSlmApiBase() when unset).
  private baseUrlOverride: string | null = null
  private defaultHeaders: Record<string, string>
  private defaultTimeout: number

  constructor() {
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    }
    this.defaultTimeout = DEFAULT_TIMEOUT_MS
  }

  // Public setter for base URL (used by plugin configuration / tests).
  setBaseUrl(url: string): void {
    this.baseUrlOverride = url
  }

  // Public setter for default timeout.
  setTimeout(timeout: number): void {
    this.defaultTimeout = timeout
  }

  getConfiguration(): Record<string, unknown> {
    return {
      baseUrl: this.resolveBaseUrl(),
      timeout: this.defaultTimeout,
    }
  }

  // ==================================================================================
  // BASE URL — resolved from getSlmApiBase() unless explicitly overridden
  // ==================================================================================

  private resolveBaseUrl(): string {
    return this.baseUrlOverride ?? getSlmApiBase()
  }

  // ==================================================================================
  // AUTH TOKEN — the one SLM reader (utils/authStorage, #17856 row 8)
  // ==================================================================================

  private getAuthToken(): string | null {
    return readSlmToken()
  }

  // Auth/MFA endpoints must never trigger a session-clearing 401 handler — a 401
  // there is a credential failure, not a rejected session.
  private isAuthEndpoint(endpoint: string): boolean {
    return endpoint.includes('/auth/') || endpoint.includes('/mfa/')
  }

  // Handle 401 — clear stored session and redirect to /login.
  // Only destructive when the request carried a bearer token: a 401 on a
  // token-less background call is not a session rejection.
  private handleUnauthorized(endpoint: string, tokenWasAttached: boolean): void {
    if (!tokenWasAttached) {
      logger.debug(
        '401 on token-less request — not clearing session (no session to invalidate):',
        endpoint
      )
      return
    }
    logger.warn('401 Unauthorized, clearing SLM session:', endpoint)
    clearSlmSession()
    if (typeof window !== 'undefined' && !isLoginPathname(window.location.pathname)) {
      window.location.href = buildLoginUrl(window.location)
    }
  }

  // ==================================================================================
  // RAW REQUEST — returns the Response object (for streaming, blobs, etc.)
  // ==================================================================================

  async rawRequest(
    endpoint: string,
    options: RequestOptions & { method?: string; body?: unknown } = {}
  ): Promise<Response> {
    const {
      method = 'GET',
      headers = {},
      body,
      timeout = this.defaultTimeout,
      signal: externalSignal,
      params,
    } = options

    const baseUrl = this.resolveBaseUrl()
    const path = withQuery(endpoint, params)
    const url = baseUrl ? `${baseUrl}${path}` : path

    const controller = new AbortController()
    let timedOut = false
    const timeoutId = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeout)

    // Forward external cancellation into the internal controller.
    let externalAbortHandler: (() => void) | null = null
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort()
      } else {
        externalAbortHandler = () => controller.abort()
        externalSignal.addEventListener('abort', externalAbortHandler)
      }
    }

    const cleanup = () => {
      clearTimeout(timeoutId)
      if (externalSignal && externalAbortHandler) {
        externalSignal.removeEventListener('abort', externalAbortHandler)
      }
    }

    try {
      const fetchOptions: RequestInit = {
        method,
        headers: { ...this.defaultHeaders, ...headers },
        signal: controller.signal,
      }

      // Inject auth token if available.
      const authToken = this.getAuthToken()
      if (authToken) {
        const hdrs = fetchOptions.headers as Record<string, string>
        hdrs['Authorization'] = `Bearer ${authToken}`
      }

      // Handle body — support FormData (don't stringify, drop Content-Type so
      // the browser sets the multipart boundary).
      if (body instanceof FormData) {
        fetchOptions.body = body
        const hdrs = fetchOptions.headers as Record<string, string>
        delete hdrs['Content-Type']
      } else if (body !== undefined) {
        fetchOptions.body = JSON.stringify(body)
      }

      const response = await fetch(url, fetchOptions)
      cleanup()

      // Handle 401 — redirect to login (skip for auth/mfa endpoints). Pass
      // whether THIS request carried a bearer token so we only clear + redirect
      // on a genuine rejection of an authenticated request.
      if (response.status === 401 && !this.isAuthEndpoint(endpoint)) {
        this.handleUnauthorized(endpoint, authToken != null)
      }

      // 503 is "could not decide" (e.g. the revocation store timed out, #18892):
      // never clear the session or redirect. The error surfaces to the caller,
      // and GET retries it with backoff (only 4xx are non-retryable).
      if (response.status === SERVICE_UNAVAILABLE_STATUS) {
        logger.warn('503 Service Unavailable, keeping SLM session (retryable):', endpoint)
      }

      return response
    } catch (error) {
      cleanup()
      if (error instanceof Error && error.name === 'AbortError') {
        if (timedOut) throw new Error(`Request timeout after ${timeout}ms`)
        throw error
      }
      throw error
    }
  }

  // ==================================================================================
  // CONVENIENCE METHODS — return parsed JSON data (not Response)
  // ==================================================================================

  // GET with retry logic and exponential backoff.
  async get<T = unknown>(endpoint: string, options: GetOptions = {}): Promise<T> {
    let lastError: Error | undefined
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3
    let attemptsMade = 0
    let retryAfterMs = 0

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      attemptsMade = attempt
      retryAfterMs = 0
      try {
        const response = await this.rawRequest(endpoint, { method: 'GET', ...options })

        if (!response.ok) {
          if (response.status === SERVICE_UNAVAILABLE_STATUS) {
            retryAfterMs = parseRetryAfterMs(response.headers.get('retry-after'))
          }
          throw await httpErrorFrom(response)
        }

        if (options.responseType === 'text') return (await response.text()) as T
        return (await response.json()) as T
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error))
        logger.debug(`GET attempt ${attempt} failed for ${endpoint}: ${lastError.message}`)

        // Don't retry 4xx client errors — they won't succeed on retry.
        if (isHttpClientError(lastError)) {
          break
        }

        if (attempt < maxRetries) {
          // Retry-After is a floor on the backoff, capped at the client's max backoff.
          const delay = Math.min(
            Math.max(backoffDelay(attempt - 1, RETRY_BACKOFF), retryAfterMs),
            RETRY_BACKOFF.max
          )
          await new Promise((resolve) => setTimeout(resolve, delay))
        }
      }
    }

    if (!options.suppressErrorLog) {
      logger.warn(
        `GET failed for ${endpoint} after ${attemptsMade} attempt(s): ${lastError?.message}`
      )
    }
    throw lastError
  }

  // GET typed by the generated contract (#16292). The path must be a GET in
  // `paths`, and the response type comes from its 200 schema, so there is no
  // inline shape assertion for TypeScript to take on trust. Contract keys carry
  // the `/api` prefix; the client's base already supplies it (or `/slm/api`).
  async getContract<P extends GetPath<paths>>(
    path: P,
    options: RequestOptions = {}
  ): Promise<GetResponse<paths, P>> {
    return (await this.get(path.replace(/^\/api(?=\/)/, ''), options)) as GetResponse<paths, P>
  }

  // POST — returns parsed JSON (handles 204 No Content).
  async post<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'POST', body: data, ...options })
    if (!response.ok) {
      throw await httpErrorFrom(response)
    }
    return parseJsonBody<T>(response)
  }

  // PUT — returns parsed JSON (handles 204 No Content).
  async put<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'PUT', body: data, ...options })
    if (!response.ok) {
      throw await httpErrorFrom(response)
    }
    return parseJsonBody<T>(response)
  }

  // PATCH — partial update, returns parsed JSON (handles 204 No Content).
  async patch<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'PATCH', body: data, ...options })
    if (!response.ok) {
      throw await httpErrorFrom(response)
    }
    return parseJsonBody<T>(response)
  }

  // DELETE — returns parsed JSON (handles empty responses).
  /** `body` is for the few APIs that take one on DELETE (#12363); most send none. */
  async delete<T = unknown>(endpoint: string, options: RequestOptions & { body?: unknown } = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'DELETE', ...options })
    if (!response.ok) {
      throw await httpErrorFrom(response)
    }
    return parseJsonBody<T>(response)
  }

  // ==================================================================================
  // FILE UPLOAD with progress tracking
  // ==================================================================================

  async uploadFile(
    endpoint: string,
    file: File,
    progressCallback: ((progress: number) => void) | null = null,
    options: { fields?: Record<string, string>; timeout?: number } = {}
  ): Promise<Record<string, unknown>> {
    const formData = new FormData()
    formData.append('file', file)

    if (options.fields) {
      Object.entries(options.fields).forEach(([key, value]) => {
        formData.append(key, value)
      })
    }

    const baseUrl = this.resolveBaseUrl()
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint
    const xhr = new XMLHttpRequest()

    return await new Promise<Record<string, unknown>>((resolve, reject) => {
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText))
          } catch {
            resolve({ success: true })
          }
        } else {
          reject(new Error(`Upload failed: HTTP ${xhr.status}`))
        }
      }

      xhr.onerror = () => reject(new Error('Upload failed: Network error'))
      xhr.ontimeout = () => reject(new Error('Upload failed: Timeout'))

      if (progressCallback) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            progressCallback(Math.round((e.loaded / e.total) * 100))
          }
        }
      }

      xhr.open('POST', url)
      const token = this.getAuthToken()
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      }
      xhr.timeout = options.timeout || this.defaultTimeout
      xhr.send(formData)
    })
  }
}

// Singleton — the canonical SLM API client. Construction is side-effect free
// (base URL is resolved lazily per request), so eager instantiation is safe.
export const slmApiClient = new SlmApiClient()

export default slmApiClient
