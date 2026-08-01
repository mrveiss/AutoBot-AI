// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared Response-builder helpers for the slmApiClient seam (#12420 Phase 2,
 * consolidated in #12654).
 *
 * The composables that route through `slmApiClient.rawRequest` resolve a Fetch
 * `Response`. Their tests mock that seam per-file (so the vi.mock factory hoists
 * correctly) and use these builders to produce Response-shaped stubs the adapter
 * (and the rawRequest-based useCodeSync methods) understand — driving the
 * `response.data` unwrap and the reproduced axios error shape.
 */

/** A minimal Fetch-Response stub the adapter understands. */
export function makeResponse(
  status: number,
  body: unknown,
  contentType = 'application/json'
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? contentType : null),
    },
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response
}

/** 2xx JSON response. */
export function jsonResponse(body: unknown, status = 200): Response {
  return makeResponse(status, body, 'application/json')
}

/** Non-2xx JSON error response (the adapter surfaces body as err.response.data). */
export function errorResponse(status: number, body: unknown): Response {
  return makeResponse(status, body, 'application/json')
}

/**
 * `(status, body)` Response stub for the rawRequest-based useCodeSync methods,
 * which inspect only `response.ok`/`response.status`/`response.json()`. A thin
 * wrapper over `makeResponse` so every test file shares one builder.
 */
export function mockResponse(status: number, body: unknown): Response {
  return makeResponse(status, body)
}
