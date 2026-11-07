// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The one HTTP transport under both apps' ApiClients (#14908, maintainer decision 2026-10-28).
// Timeout and abort, GET retry with backoff (Retry-After honoured), query params, HttpError
// and JSON/text parsing live here. Each app subclasses it for what is genuinely its own: the
// base URL, the auth token and the 401 policy, plus any app-specific headers or behaviour.

import { backoffDelay, RETRY_BACKOFF } from './backoff'
import { httpErrorFrom, isHttpClientError, parseJsonBody } from './httpError'
import type { createLogger } from './logger'

export type TransportLogger = ReturnType<typeof createLogger>

/** HTTP status for "could not decide" (e.g. a revocation check timed out): retryable, never a logout. */
export const SERVICE_UNAVAILABLE_STATUS = 503

export interface TransportRequestOptions {
  headers?: Record<string, string>
  timeout?: number
  maxRetries?: number
  signal?: AbortSignal
  /** No WARN on final GET failure: for endpoints whose absence the caller handles. */
  suppressErrorLog?: boolean
  /** A 401 is returned to the caller without the client's 401 policy running (diagnostics, #12363). */
  keepSessionOn401?: boolean
  /** Appended URL-encoded to the endpoint; `null`/`undefined` values are left out. */
  params?: Record<string, string | number | boolean | null | undefined>
  /** GET only: `'text'` returns the body as a string; anything else parses JSON. */
  responseType?: string
}

export type RawRequestOptions<O extends TransportRequestOptions> = O & { method?: string; body?: unknown }

/** Append `params` to `endpoint`, skipping null/undefined; keeps an existing `?query`. Scalars only. */
export function withQuery(endpoint: string, params: TransportRequestOptions['params']): string {
  if (!params) return endpoint
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) query.append(key, String(value))
  }
  const text = query.toString()
  if (!text) return endpoint
  return `${endpoint}${endpoint.includes('?') ? '&' : '?'}${text}`
}

/** An endpoint naming a host of its own; the request would carry the bearer to a host the client does not own. */
export class AbsoluteEndpointError extends Error {
  constructor(endpoint: string) {
    super(`Refusing to send credentials to an absolute or protocol-relative endpoint: ${endpoint}`)
    this.name = 'AbsoluteEndpointError'
  }
}

/**
 * Throws unless `endpoint` is a path on the client's own origin. Mirrors what a browser's URL parser
 * accepts as "has its own host": tab/newline are dropped anywhere and leading control/space is trimmed
 * before a `scheme:` (any case) or two slashes/backslashes (`//x`, `/\x`, `\\x`) are looked for.
 */
export function assertOwnOriginPath(endpoint: string): void {
  // eslint-disable-next-line no-control-regex
  const seen = endpoint.replace(/[\t\n\r]/g, '').replace(/^[\u0000-\u0020]+/, '')
  if (/^[a-z][a-z0-9+.-]*:/i.test(seen) || /^[\\/]{2}/.test(seen)) throw new AbsoluteEndpointError(endpoint)
}

/** A Retry-After header (delta-seconds or HTTP-date) in ms; missing, negative or unparseable is 0. */
export function parseRetryAfterMs(header: string | null, now: number = Date.now()): number {
  if (!header) return 0
  const value = header.trim()
  if (/^\d+$/.test(value)) return Number(value) * 1000
  const at = Date.parse(value)
  return Number.isNaN(at) ? 0 : Math.max(0, at - now)
}

/** One request's abort controller: fires on timeout or on the caller's signal; `cleanup` disarms both. */
function armAbort(timeout: number, external?: AbortSignal) {
  const controller = new AbortController()
  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeout)
  const onExternalAbort = () => controller.abort()
  if (external?.aborted) controller.abort()
  else external?.addEventListener('abort', onExternalAbort)
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timeoutId)
      external?.removeEventListener('abort', onExternalAbort)
    },
    /** A timeout surfaces as its own message; any other error passes through unchanged. */
    translate: (error: unknown): unknown =>
      timedOut && error instanceof Error && error.name === 'AbortError' ? new Error(`Request timeout after ${timeout}ms`) : error,
  }
}

type BodyReader = (response: Response, endpoint: string) => unknown

type GetAttempt<T> = { ok: true; value: T } | { ok: false; error: Error; retryAfterMs: number }

// ---- Typed call layer (#12363) -------------------------------------------------------------
// `Paths` is an openapi-typescript `paths` interface injected by each app; the kit stays app-agnostic.
// The path key is matched literally (no template-literal inference) to keep type-checking fast.

export type HttpMethod = 'get' | 'put' | 'post' | 'delete' | 'patch'

type OpAt<P, K extends keyof P, M extends string> = M extends keyof P[K] ? NonNullable<P[K][M]> : never

/** The methods a documented path actually offers (`get?: never` entries are excluded). */
export type MethodsOf<P, K extends keyof P> = { [M in HttpMethod]: [OpAt<P, K, M>] extends [never] ? never : M }[HttpMethod]

type JsonOf<C> = C extends { 'application/json': infer J } ? J : unknown

/** The operation's JSON 200/201 response body; `void` for a documented 204; `unknown` when it documents none. */
export type CallResponse<Op> = Op extends { responses: infer R }
  ? R extends { 200: { content: infer C } }
    ? JsonOf<C>
    : R extends { 201: { content: infer C } }
      ? JsonOf<C>
      : R extends { 204: unknown }
        ? void
        : unknown
  : unknown

/** True when `call` can read the operation's reply: a JSON 200/201 body or a 204. CSV, text and blobs go through `callRaw`. */
type ReturnsJson<Op> = Op extends { responses: infer R }
  ? R extends { 200: { content: { 'application/json': unknown } } }
    ? true
    : R extends { 201: { content: { 'application/json': unknown } } }
      ? true
      : R extends { 204: unknown }
        ? true
        : false
  : false

/** The methods of a path whose reply `call` can read (see {@link ReturnsJson}); the rest are `callRaw` only. */
export type JsonMethodsOf<P, K extends keyof P> = {
  [M in MethodsOf<P, K>]: ReturnsJson<OpAt<P, K, M>> extends true ? M : never
}[MethodsOf<P, K>]

type ParamsOf<Op, S extends 'path' | 'query'> = Op extends { parameters: infer Pa } ? (S extends keyof Pa ? NonNullable<Pa[S]> : never) : never
type BodyOf<B> = B extends { content: infer C } ? (C extends { 'application/json': infer J } ? J : FormData | Blob) : never

type PathPart<Op> = [ParamsOf<Op, 'path'>] extends [never] ? { path?: undefined } : { path: ParamsOf<Op, 'path'> }
type QueryPart<Op> = [ParamsOf<Op, 'query'>] extends [never] ? { query?: undefined } : { query?: ParamsOf<Op, 'query'> }
type BodyPart<Op> = Op extends { requestBody: infer B }
  ? { body: BodyOf<B> }
  : Op extends { requestBody?: infer B }
    ? [NonNullable<B>] extends [never] ? { body?: undefined } : { body?: BodyOf<NonNullable<B>> }
    : { body?: undefined }

/** Per-call input: `path` params, `query`, `body` typed from the operation, plus the client's transport options. */
export type CallInit<Op, O extends TransportRequestOptions> = Omit<O, 'params'> & PathPart<Op> & QueryPart<Op> & BodyPart<Op>
type CallArgs<Op, O extends TransportRequestOptions> = {} extends CallInit<Op, O> ? [init?: CallInit<Op, O>] : [init: CallInit<Op, O>]

/**
 * Substitute `{name}` segments, URL-encoded. A missing value or a key the template does not name is a
 * programming error, not a request. (Contract keys carry no `{x:path}` converter: openapi names the
 * parameter `{x}` and only prose mentions `:path`, so every value is encoded as one segment.)
 */
export function fillPathParams(template: string, params: Record<string, unknown> | undefined): string {
  const named = new Set<string>()
  const filled = template.replace(/\{([^}]+)\}/g, (_match, name: string) => {
    named.add(name)
    const value = params?.[name]
    if (value === undefined || value === null) throw new Error(`Missing path parameter "${name}" for ${template}`)
    return encodeURIComponent(String(value))
  })
  const unused = Object.keys(params ?? {}).filter((key) => !named.has(key))
  if (unused.length) throw new Error(`Unused path parameter(s) ${unused.map((k) => `"${k}"`).join(', ')} for ${template}`)
  return filled
}

/** The reply of a typed `call`: JSON, or `undefined` for a 204; anything else is a contract mismatch pointing at `callRaw`. */
function readCallBody(response: Response, endpoint: string): Promise<unknown> | undefined {
  if (response.status === 204) return undefined
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('json')) return response.json()
  throw new Error(`call() expects a JSON reply but ${endpoint} returned ${contentType || 'no content-type'}; use callRaw() for non-JSON bodies`)
}

export abstract class ApiClientBase<O extends TransportRequestOptions = TransportRequestOptions, P extends object = object> {
  protected defaultHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
  protected defaultKeepSessionOn401 = false

  constructor(
    protected defaultTimeout: number,
    protected readonly logger: TransportLogger
  ) {}

  /** The base URL requests resolve against, resolved per request (may be async). */
  protected abstract resolveBaseUrl(): string | Promise<string>
  /** The bearer token for this request, or null when there is no session. */
  protected abstract getAuthToken(): string | null
  /** An auth/login endpoint: a 401 there is a credential failure, not a rejected session. */
  protected abstract isAuthEndpoint(endpoint: string): boolean
  /** What this app does with a 401 on a non-auth endpoint (clear the session, redirect, or nothing). */
  protected abstract handleUnauthorized(endpoint: string, tokenWasAttached: boolean): void

  /** Add app-specific request headers; `headers` already holds the defaults, the caller's and the token. */
  protected decorateHeaders(_headers: Record<string, string>): void {}
  /**
   * Map a contract key to the endpoint this client sends. Identity by default; a client whose base
   * already carries part of the key (e.g. an `/api` prefix) strips it here, once, for `call` and `callRaw`.
   */
  protected contractPath(path: string): string {
    return path
  }
  /** Observe every response before it is returned (after the 401 policy). */
  protected onResponse(_response: Response, _endpoint: string): void {}
  /** A GET failure that retrying cannot fix. */
  protected isNonRetryable(error: Error): boolean {
    return isHttpClientError(error)
  }
  /** Upload timeout when the caller gives none. */
  protected uploadTimeout(): number {
    return this.defaultTimeout
  }
  /**
   * An absolute endpoint the app has itself configured as its API base and so may receive the bearer.
   * The default trusts none. An override must compare parsed origins and path segments, never a string
   * prefix; protocol-relative and backslash forms are refused before this is consulted.
   */
  protected isTrustedAbsoluteEndpoint(_endpoint: string): boolean {
    return false
  }
  /** Set auth on an upload; the default sends none. */
  protected authorizeUpload(_xhr: XMLHttpRequest): void {}

  setTimeout(timeout: number): void {
    this.defaultTimeout = timeout
  }

  /** A client whose 401 does not mean this app's session is gone surfaces the 401 instead (#10193). */
  setKeepSessionOn401(keep: boolean): void {
    this.defaultKeepSessionOn401 = keep
  }

  /** The one endpoint gate for rawRequest, get and uploadFile: own-origin paths, or an endpoint the app trusts. */
  private assertEndpointAllowed(endpoint: string): void {
    // eslint-disable-next-line no-control-regex
    const seen = endpoint.replace(/[\t\n\r]/g, '').replace(/^[\u0000-\u0020]+/, '')
    if (!/^[a-z][a-z0-9+.-]*:/i.test(seen) || /^[\\/]{2}/.test(seen)) return assertOwnOriginPath(endpoint)
    if (!this.isTrustedAbsoluteEndpoint(endpoint)) throw new AbsoluteEndpointError(endpoint)
  }

  private buildInit(opts: RawRequestOptions<O>, token: string | null, signal: AbortSignal): RequestInit {
    const headers: Record<string, string> = { ...this.defaultHeaders, ...opts.headers }
    if (token) headers['Authorization'] = `Bearer ${token}`
    this.decorateHeaders(headers)
    const init: RequestInit = { method: opts.method ?? 'GET', headers, signal }
    if (opts.body instanceof FormData) {
      init.body = opts.body
      delete headers['Content-Type'] // the browser sets the multipart boundary
    } else if (opts.body instanceof Blob) {
      init.body = opts.body // raw bytes: JSON would turn them into "{}"
    } else if (opts.body !== undefined) {
      init.body = JSON.stringify(opts.body)
    }
    return init
  }

  private applyResponsePolicy(response: Response, endpoint: string, token: string | null, keep: boolean): void {
    if (response.status === 401 && !this.isAuthEndpoint(endpoint) && !keep) {
      this.handleUnauthorized(endpoint, token != null)
    }
    this.onResponse(response, endpoint)
  }

  /** The Response itself, for streaming and blobs. Non-2xx is NOT thrown here. */
  async rawRequest(endpoint: string, options: RawRequestOptions<O> = {} as RawRequestOptions<O>): Promise<Response> {
    this.assertEndpointAllowed(endpoint)
    const baseUrl = await this.resolveBaseUrl()
    const path = withQuery(endpoint, options.params)
    const abort = armAbort(options.timeout || this.defaultTimeout, options.signal)
    try {
      const token = this.getAuthToken()
      const response = await fetch(baseUrl ? `${baseUrl}${path}` : path, this.buildInit(options, token, abort.signal))
      abort.cleanup()
      this.applyResponsePolicy(response, endpoint, token, options.keepSessionOn401 ?? this.defaultKeepSessionOn401)
      return response
    } catch (error) {
      abort.cleanup()
      throw abort.translate(error)
    }
  }

  private async attemptGet<T>(endpoint: string, options: O, read?: BodyReader): Promise<GetAttempt<T>> {
    let retryAfterMs = 0
    try {
      const response = await this.rawRequest(endpoint, { method: 'GET', ...options })
      if (!response.ok) {
        if (response.status === SERVICE_UNAVAILABLE_STATUS) retryAfterMs = parseRetryAfterMs(response.headers.get('retry-after'))
        throw await httpErrorFrom(response)
      }
      const value = read ? await read(response, endpoint) : options.responseType === 'text' ? await response.text() : await response.json()
      return { ok: true, value: value as T }
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error : new Error(String(error)), retryAfterMs }
    }
  }

  /** GET with retry and exponential backoff; Retry-After is a floor on the delay, capped at the max backoff. */
  async get<T = unknown>(endpoint: string, options: O = {} as O): Promise<T> {
    return this.getWith<T>(endpoint, options)
  }

  private async getWith<T>(endpoint: string, options: O, read?: BodyReader): Promise<T> {
    this.assertEndpointAllowed(endpoint) // a refusal is final: never retried
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3
    let lastError: Error | undefined
    let attemptsMade = 0
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      attemptsMade = attempt
      const result = await this.attemptGet<T>(endpoint, options, read)
      if (result.ok) return result.value
      lastError = result.error
      // Per-attempt failures are debug-level; one summary WARN is logged below.
      this.logger.debug(`GET attempt ${attempt} failed for ${endpoint}: ${lastError.message}`)
      if (this.isNonRetryable(lastError)) break
      if (attempt < maxRetries) {
        const delay = Math.min(Math.max(backoffDelay(attempt - 1, RETRY_BACKOFF), result.retryAfterMs), RETRY_BACKOFF.max)
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }
    if (!options.suppressErrorLog) {
      this.logger.warn(`GET failed for ${endpoint} after ${attemptsMade} attempt(s): ${lastError?.message}`)
    }
    throw lastError
  }

  private async send<T>(method: string, endpoint: string, body: unknown, options: O, read?: BodyReader): Promise<T> {
    const response = await this.rawRequest(endpoint, { method, body, ...options })
    if (!response.ok) throw await httpErrorFrom(response)
    return read ? ((await read(response, endpoint)) as T) : parseJsonBody<T>(response)
  }

  post<T = unknown>(endpoint: string, data?: unknown, options: O = {} as O): Promise<T> {
    return this.send<T>('POST', endpoint, data, options)
  }

  put<T = unknown>(endpoint: string, data?: unknown, options: O = {} as O): Promise<T> {
    return this.send<T>('PUT', endpoint, data, options)
  }

  patch<T = unknown>(endpoint: string, data?: unknown, options: O = {} as O): Promise<T> {
    return this.send<T>('PATCH', endpoint, data, options)
  }

  private splitCall(method: string, path: string, init: unknown) {
    const { path: pathParams, query, body, ...rest } = (init ?? {}) as Record<string, unknown>
    const endpoint = fillPathParams(this.contractPath(path), pathParams as Record<string, unknown> | undefined)
    const options = { ...rest, params: query } as unknown as O
    return { endpoint, options, body, verb: method.toUpperCase() }
  }

  /**
   * The typed request: `path` is a key of the app's generated contract, `init` carries the path params,
   * query and body the operation documents. Resolves to the operation's JSON 200/201 body, or `undefined`
   * for a 204. GET retries; the other methods are single-shot. Operations that reply with anything but
   * JSON (CSV, streams, blobs) are a type error here and a runtime error if the server answers non-JSON:
   * use {@link callRaw}.
   */
  call<K extends keyof P & string, M extends JsonMethodsOf<P, K>>(
    method: M,
    path: K,
    ...args: CallArgs<OpAt<P, K, M>, O>
  ): Promise<CallResponse<OpAt<P, K, M>>> {
    const { endpoint, options, body, verb } = this.splitCall(method, path, args[0])
    if (verb === 'GET') return this.getWith(endpoint, options, readCallBody) as Promise<CallResponse<OpAt<P, K, M>>>
    return this.send(verb, endpoint, body, options, readCallBody) as Promise<CallResponse<OpAt<P, K, M>>>
  }

  /** The typed request returning the `Response` itself (SSE, blobs). Non-2xx is NOT thrown here. */
  callRaw<K extends keyof P & string, M extends MethodsOf<P, K>>(
    method: M,
    path: K,
    ...args: CallArgs<OpAt<P, K, M>, O>
  ): Promise<Response> {
    const { endpoint, options, body, verb } = this.splitCall(method, path, args[0])
    return this.rawRequest(endpoint, { ...options, method: verb, body } as RawRequestOptions<O>)
  }

  /** `body` is for the few APIs that take one on DELETE (#12363); most send none. */
  delete<T = unknown>(endpoint: string, options: O & { body?: unknown } = {} as O): Promise<T> {
    return this.send<T>('DELETE', endpoint, undefined, options)
  }

  /** Settle the upload from the XHR's outcome: 2xx resolves the parsed body, anything else rejects. */
  private wireUpload(
    xhr: XMLHttpRequest,
    resolve: (body: Record<string, unknown>) => void,
    reject: (error: Error) => void,
    progressCallback: ((progress: number) => void) | null
  ): void {
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) return reject(new Error(`Upload failed: HTTP ${xhr.status}`))
      try {
        resolve(JSON.parse(xhr.responseText))
      } catch {
        resolve({ success: true })
      }
    }
    xhr.onerror = () => reject(new Error('Upload failed: Network error'))
    xhr.ontimeout = () => reject(new Error('Upload failed: Timeout'))
    if (!progressCallback) return
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) progressCallback(Math.round((e.loaded / e.total) * 100))
    }
  }

  /** POST a file as multipart with optional 0-100 progress; resolves to the parsed body (or `{success:true}`). */
  async uploadFile(
    endpoint: string,
    file: File,
    progressCallback: ((progress: number) => void) | null = null,
    options: { fields?: Record<string, string>; timeout?: number } = {}
  ): Promise<Record<string, unknown>> {
    this.assertEndpointAllowed(endpoint)
    const formData = new FormData()
    formData.append('file', file)
    for (const [key, value] of Object.entries(options.fields ?? {})) formData.append(key, value)
    const baseUrl = await this.resolveBaseUrl()
    const xhr = new XMLHttpRequest()
    return await new Promise<Record<string, unknown>>((resolve, reject) => {
      this.wireUpload(xhr, resolve, reject, progressCallback)
      xhr.open('POST', baseUrl ? `${baseUrl}${endpoint}` : endpoint)
      this.authorizeUpload(xhr)
      xhr.timeout = options.timeout || this.uploadTimeout()
      xhr.send(formData)
    })
  }
}
