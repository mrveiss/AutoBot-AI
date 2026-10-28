// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { isHttpError } from '@autobot/ui'
import i18n from '@/i18n'

/**
 * Unwrap the FastAPI `{ "detail": "..." }` error body (#13079).
 *
 * The client throws the kit `HttpError`, which keeps the parsed body; its `detail` is the
 * FastAPI message. Otherwise the caller's translated fallback leads, with the status or the
 * error's own message. The joining text is i18n too (`common.errors.*`), never a literal.
 * Callers pass a translated fallback, never `String(err)`: that would repeat the cause.
 * Re-exported from `useAutobotApi`, which stays the import path every caller uses.
 */
export function autobotApiErrorMessage(err: unknown, fallback: string): string {
  const t = i18n.global.t
  if (isHttpError(err)) {
    return err.detail || t('common.errors.withStatus', { message: fallback, status: err.status })
  }
  if (err instanceof Error && err.message.length > 0) {
    return t('common.errors.withCause', { message: fallback, cause: err.message })
  }
  return fallback
}
