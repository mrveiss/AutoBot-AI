// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared axios-compat adapter over the canonical `slmApiClient` (#12654).
 *
 * The #12420 Phase-2 migration routed every per-composable axios instance
 * through the canonical `slmApiClient`, reproducing the axios surface each
 * method body depends on via a thin adapter. That adapter (the
 * `AxiosLikeResponse` envelope, `withParams`, `adapterRequest` and the
 * get/post/put/patch/delete facade) was copied byte-for-byte into both
 * `useSlmApi` and `useRoles`. This module consolidates that single shared core
 * so it lives in ONE place; the composables import it and pass the two behaviour
 * flags that were their only real differences:
 *
 *   * `textFallback` — a non-JSON 2xx response yields `response.text()` (PEM cert
 *     downloads in useSlmApi) rather than `{}` (useRoles).
 *   * `arrays` — `withParams` serialises array values as repeated `key[]=value`
 *     (useRoles' syncRole `node_ids`) rather than axios's scalar `String(value)`.
 *
 * It delegates to `slmApiClient.rawRequest` (not the get/post/... helpers) on
 * purpose: rawRequest is the single seam that injects the bearer token + base
 * URL and runs the 401 handler, WITHOUT the helpers' GET retry/back-off or the
 * `HTTP <n>: <msg>` error transform — preserving the original single-shot,
 * structured-error behaviour every consumer relies on:
 *
 *   * methods `await client.<verb>(endpoint, body?)` and read `response.data`
 *     → the adapter returns `{ data }`.
 *   * consumers read `err.response.status` / `err.response.data.detail` on a
 *     rejected call → the adapter throws an axios-shaped error carrying
 *     `response.status` and `response.data` (and a `message` of `HTTP <n>` as the
 *     secondary fallback); a network/timeout rejection surfaces the raw Error
 *     (no `.response`), so `err.message` remains the fallback exactly as axios.
 */

import { slmApiClient } from '@/utils/ApiClient'

/** The axios `{ data }` envelope every migrated method reads via `response.data`. */
export interface AxiosLikeResponse<T> {
  data: T
}

export interface AdapterRequestOptions {
  /**
   * When true, a non-JSON 2xx body is returned as `response.text()` (mirroring
   * axios's default transform falling through to the raw string — used for PEM
   * cert downloads). When false/omitted the adapter returns `{}` for non-JSON 2xx.
   */
  textFallback?: boolean
}

/**
 * Shared core: route one call through `slmApiClient.rawRequest` and reproduce the
 * axios `{ data }` / `err.response` surface exactly.
 */
export async function adapterRequest<T>(
  method: string,
  endpoint: string,
  body?: unknown,
  opts?: AdapterRequestOptions
): Promise<AxiosLikeResponse<T>> {
  const response = await slmApiClient.rawRequest(endpoint, { method, body })

  if (!response.ok) {
    let data: unknown = null
    try {
      data = await response.json()
    } catch {
      /* non-JSON error body — leave data null, mirroring axios */
    }
    const error = new Error(`HTTP ${response.status}`) as Error & {
      response: { status: number; data: unknown }
    }
    // Reproduce the axios error shape consumers read (err.response.status/.data).
    error.response = { status: response.status, data }
    throw error
  }

  if (response.status === 204) return { data: {} as T }
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return { data: (await response.json()) as T }
  }
  // Non-JSON 2xx (e.g. PEM cert downloads) — useSlmApi returns the raw text as
  // axios does when its JSON transform cannot parse the payload; useRoles returns
  // an empty object.
  if (opts?.textFallback) {
    return { data: (await response.text()) as unknown as T }
  }
  return { data: {} as T }
}

export interface WithParamsOptions {
  /**
   * When true, array values are serialised as repeated `key[]=value` (axios's
   * default array serialisation; URLSearchParams encodes the brackets to
   * `%5B%5D`). When false/omitted, arrays fall through to `String(value)` — the
   * scalar path, matching call sites that never pass arrays.
   */
  arrays?: boolean
}

/**
 * Serialise an axios-style params object onto the endpoint. Scalars serialise as
 * `key=value`; arrays serialise as repeated `key[]=value` when `arrays` is set.
 */
export function withParams(
  endpoint: string,
  params?: Record<string, unknown>,
  opts?: WithParamsOptions
): string {
  if (!params) return endpoint
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (opts?.arrays && Array.isArray(value)) {
      for (const item of value) usp.append(`${key}[]`, String(item))
    } else {
      usp.append(key, String(value))
    }
  }
  const qs = usp.toString()
  if (!qs) return endpoint
  return endpoint.includes('?') ? `${endpoint}&${qs}` : `${endpoint}?${qs}`
}

export interface AxiosCompatClientOptions extends AdapterRequestOptions, WithParamsOptions {}

/** Optional per-call config carrying an axios-style `params` object. */
export interface AxiosCompatConfig {
  params?: Record<string, unknown>
}

/** The axios-compatible facade over slmApiClient consumed by the composables. */
export interface AxiosCompatClient {
  get: <T = unknown>(endpoint: string, config?: AxiosCompatConfig) => Promise<AxiosLikeResponse<T>>
  post: <T = unknown>(
    endpoint: string,
    body?: unknown,
    config?: AxiosCompatConfig
  ) => Promise<AxiosLikeResponse<T>>
  put: <T = unknown>(endpoint: string, body?: unknown) => Promise<AxiosLikeResponse<T>>
  patch: <T = unknown>(endpoint: string, body?: unknown) => Promise<AxiosLikeResponse<T>>
  delete: <T = unknown>(endpoint: string, config?: AxiosCompatConfig) => Promise<AxiosLikeResponse<T>>
}

/**
 * Build the axios-compatible facade. `textFallback`/`arrays` tune the two
 * behaviours that differed between the original per-composable copies; every
 * other aspect is identical. `post`/`delete`/`get` accept an optional
 * `{ params }` config (a superset — call sites that never pass one are
 * unaffected, since `withParams(endpoint, undefined)` returns the endpoint
 * unchanged).
 */
export function makeAxiosCompatClient(opts: AxiosCompatClientOptions = {}): AxiosCompatClient {
  const wp = (endpoint: string, params?: Record<string, unknown>): string =>
    withParams(endpoint, params, { arrays: opts.arrays })
  const req = <T>(method: string, endpoint: string, body?: unknown): Promise<AxiosLikeResponse<T>> =>
    adapterRequest<T>(method, endpoint, body, { textFallback: opts.textFallback })
  return {
    get: <T = unknown>(endpoint: string, config?: AxiosCompatConfig) =>
      req<T>('GET', wp(endpoint, config?.params)),
    post: <T = unknown>(endpoint: string, body?: unknown, config?: AxiosCompatConfig) =>
      req<T>('POST', wp(endpoint, config?.params), body ?? undefined),
    put: <T = unknown>(endpoint: string, body?: unknown) => req<T>('PUT', endpoint, body),
    patch: <T = unknown>(endpoint: string, body?: unknown) => req<T>('PATCH', endpoint, body),
    delete: <T = unknown>(endpoint: string, config?: AxiosCompatConfig) =>
      req<T>('DELETE', wp(endpoint, config?.params)),
  }
}
