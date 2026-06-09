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
