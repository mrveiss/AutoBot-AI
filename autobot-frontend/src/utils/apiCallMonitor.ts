// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Per-call RUM tracking for the shared ApiClient (#21583).
 *
 * Replaces the unloaded `ApiClientMonitor.js` Proxy: every kit-client fetch verb (get, post, put, delete,
 * rawRequest) is timed and handed to RumAgent (`window.rum`). XHR uploads (`ApiClientBase.uploadFile` /
 * `wireUpload`) and callers that use `fetch` directly bypass it. A client or fetch timeout is passed to
 * `trackApiCall` as a timeout, so its records carry it and RumAgent reports it once as a critical `api_timeout`
 * issue. A timeout is recognised by type (`isRequestTimeout`), never by message text. Connectivity failures are already
 * reported once, throttled, by the fetch interceptor in `plugins/errorHandler.ts`, so
 * they are not reported a second time here.
 */

import { createLogger } from '@/utils/debugUtils'
import { isRequestTimeout } from '@/utils/errorExtract'

const logger = createLogger('apiCallMonitor')

function isAbort(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: unknown }).name === 'AbortError'
}

function record(method: string, url: string, startTime: number, status: number | string, error?: Error, timedOut = false): void {
  const rum = typeof window === 'undefined' ? undefined : window.rum
  if (!rum) return
  try {
    rum.trackApiCall(method, url, startTime, performance.now(), status, error, timedOut)
  } catch (monitorError) {
    // Telemetry must never change the outcome of the request it observes.
    logger.warn('RUM tracking failed:', monitorError)
  }
}

/** Run one request, record it with RumAgent, and return or rethrow its outcome unchanged. */
export async function monitorApiCall(method: string, url: string, send: () => Promise<Response>): Promise<Response> {
  const startTime = performance.now()
  try {
    const response = await send()
    record(method, url, startTime, response.status)
    return response
  } catch (error) {
    // An abort on unmount or navigation is the caller's own doing, not a failed call.
    // Classify the thrown value itself: a DOMException from AbortSignal.timeout() is not always `instanceof Error`
    // (cross-realm, jsdom), and re-wrapping it would drop the `TimeoutError` name the classification reads.
    if (!isAbort(error)) {
      record(method, url, startTime, 'error', error instanceof Error ? error : new Error(String(error)), isRequestTimeout(error))
    }
    throw error
  }
}
