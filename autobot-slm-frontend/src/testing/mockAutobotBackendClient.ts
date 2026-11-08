// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The one test double for the SLM's main-backend client (#12363).
 *
 * `createAutobotBackendClient()` builds an `SlmApiClient` pointed at the main backend.
 * A test replaces that class, keeps the rest of `@/utils/ApiClient` real, and drives
 * the recorded methods:
 *
 *   vi.mock('@/utils/ApiClient', (importOriginal) => withMockedBackendClient(importOriginal))
 *   import { backendClient } from '@/testing/mockAutobotBackendClient'
 *
 * The methods resolve with the parsed body (not an axios `{ data }` envelope), and a
 * failure is a kit `HttpError`. Token and 401 handling are the real client's, tested
 * in `utils/ApiClient.test.ts`.
 */

import { vi } from 'vitest'

export const backendClient = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  rawRequest: vi.fn(),
  /** The base URL the last client was pointed at. */
  baseUrl: null as string | null,
  /** The last client's `setKeepSessionOn401` setting. */
  keepSessionOn401: null as boolean | null,
}

class MockSlmApiClient {
  get = backendClient.get
  post = backendClient.post
  put = backendClient.put
  patch = backendClient.patch
  delete = backendClient.delete
  rawRequest = backendClient.rawRequest
  setBaseUrl(url: string): void {
    backendClient.baseUrl = url
  }
  setKeepSessionOn401(keep: boolean): void {
    backendClient.keepSessionOn401 = keep
  }
}

/** A `vi.mock('@/utils/ApiClient', …)` factory: the real module, with `SlmApiClient` replaced. */
export async function withMockedBackendClient(
  importOriginal: () => Promise<unknown>,
): Promise<Record<string, unknown>> {
  return { ...(await importOriginal() as Record<string, unknown>), SlmApiClient: MockSlmApiClient }
}
