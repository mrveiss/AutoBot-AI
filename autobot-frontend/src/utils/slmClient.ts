// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Canonical SLM bridge for the MAIN frontend (#12614, #12363).
 *
 * The main `autobot-frontend` talks to two distinct backends:
 *  - the app backend, via `apiClient` (app JWT, app base URL);
 *  - the SLM control plane, via `getSLMUrl()` (a *separate* backend with its own
 *    token and base URL).
 *
 * SLM calls MUST NOT flow through `apiClient` -- that would attach the wrong JWT and resolve
 * the wrong base URL. This is the kit's `ApiClientBase` (timeout and abort, GET retry, HttpError,
 * JSON bodies) bound to the SLM origin and its own token; it owns no fetch of its own.
 *
 *  - Base URL is resolved from `getSLMUrl()` on every request. Callers pass the full path
 *    (including the `/api/...` prefix), so URL construction is preserved across the migration.
 *  - The SLM token differs per caller: `useHostInventory` sends none, while `useTLSCredentials`
 *    holds an in-memory token. There is NO shared SLM token storage key in the main frontend, so
 *    the token is supplied per client via a constructor getter (read live on each request).
 *  - A 401 from the SLM never ends the MAIN app's session: `defaultKeepSessionOn401` is on and
 *    the 401 policy does nothing (the caller sees the HttpError).
 */

import { ApiClientBase, getEnvPositiveInt, type TransportRequestOptions } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import { getSLMUrl } from '@/config/ssot-config'

const logger = createLogger('SlmClient')

// Same env-backed default the SLM app's own client uses (30 s when unset).
const DEFAULT_TIMEOUT_MS = getEnvPositiveInt(import.meta.env, 'VITE_SLM_API_TIMEOUT_MS', 30_000)

export class SlmClient extends ApiClientBase<TransportRequestOptions> {
  private readonly getToken: () => string | null

  /**
   * @param getToken supplies the SLM bearer token, read live on each request.
   *   Defaults to none (matching callers that hit token-less SLM endpoints).
   */
  constructor(getToken: () => string | null = () => null) {
    super(DEFAULT_TIMEOUT_MS, logger)
    this.getToken = getToken
    this.defaultKeepSessionOn401 = true
  }

  protected resolveBaseUrl(): string {
    return getSLMUrl()
  }

  protected getAuthToken(): string | null {
    return this.getToken()
  }

  protected isAuthEndpoint(endpoint: string): boolean {
    return endpoint.includes('/auth/')
  }

  // The main app's session is not the SLM's: nothing to clear or redirect.
  protected handleUnauthorized(): void {}
}

// Default singleton -- token-less SLM client for callers that hit token-less
// endpoints. Callers needing a token construct their own `new SlmClient(getter)`.
export const slmClient = new SlmClient()

export default slmClient
