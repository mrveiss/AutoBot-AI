// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Shared error extraction utilities for converting unknown caught errors
 * into user-friendly messages. Used across composables and services.
 * Issue #2861: Replaces `catch (err: any)` patterns with type-safe extraction.
 */

interface AxiosLikeError {
  response?: {
    data?: {
      detail?: string
      message?: string
    }
  }
  message?: string
}

function isAxiosLikeError(err: unknown): err is AxiosLikeError {
  return (
    typeof err === 'object' &&
    err !== null &&
    'response' in err
  )
}

export function extractApiErrorMessage(err: unknown, fallback: string): string {
  if (isAxiosLikeError(err)) {
    const detail = err.response?.data?.detail
    if (detail) return detail
    const message = err.response?.data?.message
    if (message) return message
  }
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}

export function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}

// ==================== Failed-response bodies (#17528) ====================

/**
 * How much of an unrecognised error body is worth showing a user.
 *
 * A recognised shape is already a sentence written for a human, so it is never
 * truncated. This cap applies only to the fallback branch, where the body could
 * be a stack trace or a proxy's diagnostic page.
 */
const MAX_UNSTRUCTURED_DETAIL = 300

/** Pull a human-readable string out of one of the backend's error shapes. */
function detailFromPayload(payload: unknown): string {
  if (typeof payload === 'string') return payload.trim()
  if (!payload || typeof payload !== 'object') return ''

  // FastAPI's request-validation 422: detail is a list of per-field errors.
  if (Array.isArray(payload)) {
    return payload
      .map(item => {
        if (typeof item === 'string') return item
        const msg = (item as Record<string, unknown>)?.msg
        return typeof msg === 'string' ? msg : ''
      })
      .filter(Boolean)
      .join('; ')
  }

  const obj = payload as Record<string, unknown>

  // `_raise_or_return_error` wraps APIErrorResponse.to_dict(), so the sentence
  // sits at error.message rather than at the top level.
  const nested = obj.error
  if (nested && typeof nested === 'object') {
    const message = (nested as Record<string, unknown>).message
    if (typeof message === 'string' && message.trim()) return message.trim()
  }

  for (const key of ['detail', 'error', 'message'] as const) {
    const value = obj[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (value && typeof value === 'object') {
      const inner = detailFromPayload(value)
      if (inner) return inner
    }
  }
  return ''
}

/**
 * What the server said about a failed response, or `''` when it said nothing usable.
 *
 * `ApiRepository` used to throw ``HTTP ${status}: ${statusText}`` without ever reading
 * the body, so every explanation the backend computed was discarded one layer above the
 * UI (#17528). The knowledge upload endpoint is where that cost most: it distinguishes
 * "scanned PDF, needs OCR" from "empty file" (#13884), names the 10MB limit and lists the
 * accepted extensions — and a user saw "HTTP 400: Bad Request" for all three.
 *
 * Reads the body as text exactly once, then parses. A proxy that rejects a request before
 * it reaches the app answers in HTML (#12311), which is not a sentence for a user, so it
 * is dropped rather than rendered as markup.
 *
 * Returns `''` rather than throwing on every failure path: this runs while an error is
 * already being constructed, and a throw here would replace a diagnosable failure with an
 * undiagnosable one.
 */
export async function extractResponseErrorDetail(response: Response): Promise<string> {
  let body: string
  try {
    body = await response.text()
  } catch {
    return ''
  }
  const trimmed = body.trim()
  if (!trimmed) return ''

  // A body that parses as JSON is answered from its own shape and never falls through:
  // `{"ok":false}` carries no sentence, and returning its source text would put raw JSON
  // in front of a user instead of an explanation.
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    // Not JSON — the unstructured branch below is the only one left.
    if (trimmed.startsWith('<')) return ''
    return trimmed.length > MAX_UNSTRUCTURED_DETAIL
      ? `${trimmed.slice(0, MAX_UNSTRUCTURED_DETAIL)}…`
      : trimmed
  }
  return detailFromPayload(parsed)
}

/**
 * The message to throw for a failed response: the status line, then the reason.
 *
 * The status line stays FIRST and verbatim because 16 call sites branch on it —
 * `ErrorHandler.js` maps 400/401/403/404/429/5xx to user-facing copy, `ApiClient.ts:425`
 * decides retries on `includes('HTTP 4')`, and `useLlcCompanyStore.ts` uses
 * `startsWith('HTTP 503')`. Appending keeps every one of those matching; replacing the
 * message would have broken them all with nothing failing to say so.
 */
export async function describeFailedResponse(response: Response): Promise<string> {
  const statusLine = `HTTP ${response.status}: ${response.statusText}`
  const detail = await extractResponseErrorDetail(response)
  return detail ? `${statusLine} — ${detail}` : statusLine
}
