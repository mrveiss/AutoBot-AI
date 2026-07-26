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
 *  - Auth token read exactly as existing SLM fetch/axios sites do:
 *    `sessionStorage.getItem('slm_access_token')` with a `localStorage`
 *    fallback (mirrors `stores/auth.ts` token initialisation).
 *  - 401 handling matches SLM's convention: clear the session keys and redirect
 *    to `/login` (the target of `authStore.logout()`), but only when the request
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

const logger = createLogger('SlmApiClient')

// SLM auth storage keys — kept in sync with stores/auth.ts (TOKEN_KEY/USER_KEY).
const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

// Login route users are redirected to on session rejection (authStore.logout()).
const LOGIN_PATH = '/login'

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
}

export interface ErrorInfo {
  status: number
  message: string
  details: Record<string, unknown> | null
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
  // AUTH TOKEN — mirrors stores/auth.ts init (sessionStorage, localStorage fallback)
  // ==================================================================================

  private getAuthToken(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
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
    try {
      sessionStorage.removeItem(TOKEN_KEY)
      sessionStorage.removeItem(USER_KEY)
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {
      /* storage unavailable — nothing to clear */
    }
    if (
      typeof window !== 'undefined' &&
      !window.location.pathname.includes(LOGIN_PATH)
    ) {
      window.location.href = LOGIN_PATH
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
    } = options

    const baseUrl = this.resolveBaseUrl()
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint

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

  private async extractErrorInfo(response: Response): Promise<ErrorInfo> {
    try {
      const errorData = await response.json()
      return {
        status: response.status,
        message: (() => {
          const raw = errorData.error || errorData.message || errorData.detail
          if (raw == null) return JSON.stringify(errorData) || 'Unknown error'
          return typeof raw === 'string' ? raw : JSON.stringify(raw)
        })(),
        details: errorData,
      }
    } catch {
      return {
        status: response.status,
        message: response.statusText || 'Unknown error',
        details: null,
      }
    }
  }

  private async parseJsonBody<T>(response: Response): Promise<T> {
    if (response.status === 204) return {} as T
    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      return (await response.json()) as T
    }
    return {} as T
  }

  // GET with retry logic and exponential backoff.
  async get<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    let lastError: Error | undefined
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3
    let attemptsMade = 0

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      attemptsMade = attempt
      try {
        const response = await this.rawRequest(endpoint, { method: 'GET', ...options })

        if (!response.ok) {
          const errorData = await this.extractErrorInfo(response)
          throw new Error(`HTTP ${response.status}: ${errorData.message}`)
        }

        return (await response.json()) as T
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error))
        logger.debug(`GET attempt ${attempt} failed for ${endpoint}: ${lastError.message}`)

        // Don't retry 4xx client errors — they won't succeed on retry.
        if (lastError.message.includes('HTTP 4')) {
          break
        }

        if (attempt < maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000)
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

  // POST — returns parsed JSON (handles 204 No Content).
  async post<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'POST', body: data, ...options })
    if (!response.ok) {
      const errorData = await this.extractErrorInfo(response)
      throw new Error(`HTTP ${response.status}: ${errorData.message}`)
    }
    return this.parseJsonBody<T>(response)
  }

  // PUT — returns parsed JSON (handles 204 No Content).
  async put<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'PUT', body: data, ...options })
    if (!response.ok) {
      const errorData = await this.extractErrorInfo(response)
      throw new Error(`HTTP ${response.status}: ${errorData.message}`)
    }
    return this.parseJsonBody<T>(response)
  }

  // PATCH — partial update, returns parsed JSON (handles 204 No Content).
  async patch<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'PATCH', body: data, ...options })
    if (!response.ok) {
      const errorData = await this.extractErrorInfo(response)
      throw new Error(`HTTP ${response.status}: ${errorData.message}`)
    }
    return this.parseJsonBody<T>(response)
  }

  // DELETE — returns parsed JSON (handles empty responses).
  async delete<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, { method: 'DELETE', ...options })
    if (!response.ok) {
      const errorData = await this.extractErrorInfo(response)
      throw new Error(`HTTP ${response.status}: ${errorData.message}`)
    }
    return this.parseJsonBody<T>(response)
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
