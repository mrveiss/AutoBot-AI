// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Canonical SLM bridge for the MAIN frontend (#12614).
 *
 * The main `autobot-frontend` talks to two distinct backends:
 *  - the app backend, via `apiClient` / `fetchWithAuth` (app JWT, app base URL);
 *  - the SLM control plane, via `getSLMUrl()` (a *separate* backend with its own
 *    token and base URL).
 *
 * SLM calls MUST NOT flow through `apiClient`/`fetchWithAuth` — that would attach
 * the wrong JWT and resolve the wrong base URL. Before this bridge, SLM callers
 * (`useHostInventory`, `useTLSCredentials`) each re-implemented raw
 * `getSLMUrl() + fetch` plumbing. This module is the single canonical client for
 * those callers, mirroring the SHAPE of `autobot-slm-frontend/src/utils/ApiClient.ts`
 * (`slmApiClient`) but scoped to only what the main-frontend SLM callers need.
 *
 *  - Base URL is resolved lazily from `getSLMUrl()` on every request. Callers pass
 *    the full path (including the `/api/...` prefix), exactly as they build it
 *    today, so URL construction is byte-for-byte preserved across the migration.
 *  - The SLM token differs per caller: `useHostInventory` sends none, while
 *    `useTLSCredentials` holds an in-memory token. There is NO shared SLM token
 *    storage key in the main frontend, so the token is supplied per client via a
 *    constructor getter (read live on each request) rather than a global lookup —
 *    avoiding cross-caller token contamination through a shared singleton.
 *  - Errors surface as `Error(detail | message | error | "HTTP <status>: <text>")`.
 */

import { createLogger } from '@/utils/debugUtils'
import { getSLMUrl } from '@/config/ssot-config'

const logger = createLogger('SlmClient')

export interface SlmRequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: unknown
  signal?: AbortSignal
  /**
   * Skip SLM-token injection for this request (e.g. the token-acquisition
   * endpoint, which authenticates via credentials, not a bearer token).
   */
  skipAuth?: boolean
}

// A body that must be passed to fetch verbatim (no JSON.stringify, no forced
// JSON Content-Type — the browser/caller owns the encoding).
function isRawBody(body: unknown): body is BodyInit {
  return (
    typeof body === 'string' ||
    body instanceof URLSearchParams ||
    body instanceof FormData ||
    body instanceof Blob ||
    body instanceof ArrayBuffer
  )
}

export class SlmClient {
  private readonly getToken: () => string | null

  /**
   * @param getToken supplies the SLM bearer token, read live on each request.
   *   Defaults to none (matching callers that hit token-less SLM endpoints).
   */
  constructor(getToken: () => string | null = () => null) {
    this.getToken = getToken
  }

  private resolveBaseUrl(): string {
    return getSLMUrl()
  }

  // ==========================================================================
  // RAW REQUEST — returns the Response (for callers that read the body/status
  // themselves, e.g. token acquisition or no-content deletes).
  // ==========================================================================

  async rawRequest(path: string, options: SlmRequestOptions = {}): Promise<Response> {
    const { method = 'GET', headers = {}, body, signal, skipAuth = false } = options
    const url = `${this.resolveBaseUrl()}${path}`

    const hdrs: Record<string, string> = { ...headers }
    const rawBody = isRawBody(body)
    // Only default the JSON Content-Type for JSON-serialised bodies; leave raw
    // bodies (form-encoded, multipart) to set their own encoding.
    if (!rawBody && hdrs['Content-Type'] == null) {
      hdrs['Content-Type'] = 'application/json'
    }

    if (!skipAuth && hdrs['Authorization'] == null) {
      const token = this.getToken()
      if (token) hdrs['Authorization'] = `Bearer ${token}`
    }

    const fetchBody: BodyInit | undefined =
      body === undefined ? undefined : rawBody ? (body as BodyInit) : JSON.stringify(body)

    return fetch(url, { method, headers: hdrs, body: fetchBody, signal })
  }

  // ==========================================================================
  // ERROR / BODY parsing
  // ==========================================================================

  private async toError(response: Response): Promise<Error> {
    const data = await response.json().catch((err) => {
      logger.warn('Failed to parse SLM error response: %s', err)
      return {} as Record<string, unknown>
    })
    const raw = (data as Record<string, unknown>).detail
      ?? (data as Record<string, unknown>).message
      ?? (data as Record<string, unknown>).error
    if (typeof raw === 'string' && raw.length > 0) return new Error(raw)
    return new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  // Parse a body that may legitimately be empty (204 / no JSON content-type).
  private async parseJsonBody<T>(response: Response): Promise<T> {
    if (response.status === 204) return {} as T
    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      return (await response.json()) as T
    }
    return {} as T
  }

  // ==========================================================================
  // CONVENIENCE METHODS — return parsed JSON, throw on non-OK.
  // ==========================================================================

  async get<T = unknown>(path: string, options: SlmRequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(path, { ...options, method: 'GET' })
    if (!response.ok) throw await this.toError(response)
    return (await response.json()) as T
  }

  async post<T = unknown>(path: string, body?: unknown, options: SlmRequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(path, { ...options, method: 'POST', body })
    if (!response.ok) throw await this.toError(response)
    return this.parseJsonBody<T>(response)
  }

  async patch<T = unknown>(path: string, body?: unknown, options: SlmRequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(path, { ...options, method: 'PATCH', body })
    if (!response.ok) throw await this.toError(response)
    return this.parseJsonBody<T>(response)
  }

  async delete<T = unknown>(path: string, options: SlmRequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(path, { ...options, method: 'DELETE' })
    if (!response.ok) throw await this.toError(response)
    return this.parseJsonBody<T>(response)
  }
}

// Default singleton — token-less SLM client for callers that hit token-less
// endpoints. Callers needing a token construct their own `new SlmClient(getter)`.
export const slmClient = new SlmClient()

export default slmClient
