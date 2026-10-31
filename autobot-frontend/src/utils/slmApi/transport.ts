// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The `slmApi` seam (#19834, ADR 011 section 4): one request function for the SLM control plane,
 * built on the main-app `ApiClient` and typed by the generated SLM contract
 * (`@autobot/slm-contract/generated`). Path and method are constrained to the contract's `paths`,
 * and the response type is read from the declared 200/201 body, so a route the SLM backend does
 * not declare does not compile. This is the same shape as `planRequest` (workflowPlanRequest.ts).
 *
 * One session, no second client class. The client is a dedicated `ApiClient` instance (its
 * session token is the main-app one, `readStoredAuthToken`; a 401 clears that session; a GET
 * retries a 503) whose base URL is the page origin: the main client's own base is the app backend
 * host, which in direct mode does not serve `/slm/api`. Nothing here reads `slm_access_token`.
 */
import type { paths } from '@autobot/slm-contract/generated'
import { ApiClient } from '@/utils/ApiClient'

/** Where nginx serves the SLM API on the page origin. The contract's own prefix is `/api`. */
export const SLM_API_PREFIX = '/slm/api'
const CONTRACT_PREFIX = '/api'

type Verb = 'get' | 'post' | 'put' | 'patch' | 'delete'
type Query = Record<string, string | number | boolean | undefined>

/** A path the SLM contract declares. */
export type SlmPath = Extract<keyof paths, `${typeof CONTRACT_PREFIX}/${string}`>

type JsonBody<O> = O extends { content: { 'application/json': infer J } } ? J : void
type OkBody<R> = R extends { 200: infer O } ? JsonBody<O> : R extends { 201: infer O } ? JsonBody<O> : void

/** The declared success body of `METHOD path` in the generated contract. */
export type SlmResponse<P extends SlmPath, V extends Verb> = paths[P][V] extends { responses: infer R }
  ? OkBody<R>
  : never

/** True where the contract declares no usable body (`unknown`, or a bare string-keyed object). */
type Undeclared<B> = unknown extends B ? true : {} extends B ? true : false // eslint-disable-line @typescript-eslint/no-empty-object-type

export interface SlmRequestInit {
  /** Values for the `{name}` placeholders of the path; each is URL-encoded. */
  params?: Record<string, string>
  query?: Query
  body?: unknown
}

let client: ApiClient | null = null

/** The one SLM client: created on first use, so importing a store builds nothing. */
export function slmClient(): ApiClient {
  if (!client) {
    client = new ApiClient()
    client.setBaseUrl(window.location.origin)
  }
  return client
}

/** Fills `{name}` placeholders of a declared path; every value is URL-encoded. */
export function fillPath(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(params[name] ?? ''))
}

/** `/api/nodes/{node_id}` in the contract is `/slm/api/nodes/<id>` on the wire. */
export function slmUrl(path: SlmPath, params: Record<string, string> = {}): string {
  return `${SLM_API_PREFIX}${fillPath(path.slice(CONTRACT_PREFIX.length), params)}`
}

/** A WebSocket URL on the SLM API, on the page origin like every other SLM request. */
export function slmWsUrl(route: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}${SLM_API_PREFIX}${route}`
}

function definedQuery(query: Query | undefined): Query | undefined {
  if (!query) return undefined
  return Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined))
}

function send(verb: Verb, url: string, init: SlmRequestInit): Promise<unknown> {
  const http = slmClient()
  const params = definedQuery(init.query)
  if (verb === 'get') return http.get(url, { params })
  if (verb === 'delete') return http.delete(url, { params })
  return http[verb](url, init.body, { params })
}

/** A call whose path, method and response all come from the contract. The one cast is here. */
export async function slmRequest<P extends SlmPath, V extends Verb & keyof paths[P]>(
  verb: V & Verb,
  path: P,
  init: SlmRequestInit = {},
): Promise<SlmResponse<P, V & Verb>> {
  const data = await send(verb, slmUrl(path, init.params), init)
  return data as SlmResponse<P, V & Verb>
}

/**
 * A call to a route whose 200 body the contract leaves undeclared (`unknown`, or a bare
 * `{[key]: unknown}`): the adapter states the shape, here, once. For a route with a declared
 * body the return type is `never`, so the declared body cannot be overridden by accident.
 */
export async function slmRequestAs<T, P extends SlmPath, V extends Verb & keyof paths[P]>(
  verb: V & Verb,
  path: P,
  init: SlmRequestInit = {},
): Promise<Undeclared<SlmResponse<P, V & Verb>> extends true ? T : never> {
  const data = await send(verb, slmUrl(path, init.params), init)
  return data as Undeclared<SlmResponse<P, V & Verb>> extends true ? T : never
}
