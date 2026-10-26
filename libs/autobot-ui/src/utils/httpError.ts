// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// HttpError — what a canonical API client throws for a non-2xx response (#12363).
// Both apps' clients threw a bare `Error('HTTP <status>: <message>')`, so a caller
// that needed the status or the backend's `detail` had to parse the message, or
// reached for a second client (axios) whose errors kept them. This keeps the exact
// message (existing checks such as `message.includes('HTTP 4')` still hold) and adds
// the parsed fields.

export class HttpError extends Error {
  /** The response status, e.g. 404. */
  readonly status: number
  /** The parsed error body, or null when it was not JSON. */
  readonly details: Record<string, unknown> | null

  constructor(status: number, message: string, details: Record<string, unknown> | null = null) {
    super(`HTTP ${status}: ${message}`)
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
