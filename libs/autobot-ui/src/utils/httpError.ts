// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// HttpError — what both apps' canonical API clients throw for a non-2xx response (#12363).
// They threw a bare `Error('HTTP <status>: <message>')`, so a caller needing the status or
// the backend's `detail` parsed the message or reached for axios. The message text is kept
// for logs and display; read `status` / `detail` instead of parsing it.

export class HttpError extends Error {
  /** The response status, e.g. 404. */
  readonly status: number
  /** The parsed error body, or null when it was not JSON. */
  readonly details: Record<string, unknown> | null

  constructor(status: number, message: string | undefined, details: Record<string, unknown> | null = null) {
    super(message ? `HTTP ${status}: ${message}` : `HTTP ${status}`)
    this.name = 'HttpError'
    this.status = status
    this.details = details
  }

  /** The backend's own `detail` text when it sent one (FastAPI's error shape), else null. */
  get detail(): string | null {
    const raw = this.details?.detail
    if (raw == null) return null
    return typeof raw === 'string' ? raw : JSON.stringify(raw)
  }
}

/** Narrowing helper for catch blocks: `if (isHttpError(e) && e.status === 404)`. */
export function isHttpError(value: unknown): value is HttpError {
  return value instanceof HttpError
}

/** A 4xx HttpError: the request itself was wrong, so retrying it cannot succeed. */
export function isHttpClientError(value: unknown): value is HttpError {
  return isHttpError(value) && value.status >= 400 && value.status < 500
}

/** Status, message and parsed body of a failed Response (both apps' clients, #12363). */
export interface ErrorInfo {
  status: number
  message: string
  details: Record<string, unknown> | null
}

/** Read a failed Response: the message is the body's `error`, `message` or `detail`. */
export async function extractErrorInfo(response: Response): Promise<ErrorInfo> {
  try {
    const errorData = await response.json()
    const raw = errorData.error || errorData.message || errorData.detail
    const message = raw == null ? JSON.stringify(errorData) || 'Unknown error' : typeof raw === 'string' ? raw : JSON.stringify(raw)
    return { status: response.status, message, details: errorData }
  } catch {
    return { status: response.status, message: response.statusText || 'Unknown error', details: null }
  }
}

/** The HttpError a client throws for a non-2xx Response: `throw await httpErrorFrom(response)`. */
export async function httpErrorFrom(response: Response): Promise<HttpError> {
  const info = await extractErrorInfo(response)
  return new HttpError(response.status, info.message, info.details)
}

/** A 2xx body as JSON; a 204 or a non-JSON body reads as `{}`. */
export async function parseJsonBody<T>(response: Response): Promise<T> {
  if (response.status === 204) return {} as T
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) return (await response.json()) as T
  return {} as T
}
