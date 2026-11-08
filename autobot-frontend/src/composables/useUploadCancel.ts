// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * User cancel for chat attachment uploads (#20133).
 *
 * Each in-flight upload owns an AbortController; aborting it rejects the transport with a `cancelled`
 * `ConversationUploadError`. A cancelled upload is dropped from the progress list and announced with
 * a notice, never shown as a failed row.
 */
import { getCurrentScope, onScopeDispose, reactive } from 'vue'
import { ConversationUploadError } from '@/utils/conversationFileUpload'

export const isUploadCancelled = (error: unknown): boolean =>
  error instanceof ConversationUploadError && error.code === 'cancelled'

export function useUploadCancel<T extends { id: string; error?: string }>(onCancelled: (upload: T) => void) {
  const aborts = reactive(new Map<string, AbortController>())
  let disposed = false

  /** Registers an upload and returns the signal to hand the transport. */
  const begin = (upload: T): AbortSignal => {
    const controller = new AbortController()
    aborts.set(upload.id, controller)
    return controller.signal
  }

  /** Releases the upload; reports it cancelled and returns true when `error` was a user cancel. */
  const settle = (upload: T, error?: unknown): boolean => {
    aborts.delete(upload.id)
    const cancelled = isUploadCancelled(error)
    if (cancelled && !disposed) onCancelled(upload)
    return cancelled
  }

  const isCancellable = (upload: T): boolean => !upload.error && aborts.has(upload.id)
  const cancel = (uploadId: string): void => aborts.get(uploadId)?.abort()

  // Unmount aborts every in-flight upload; the resulting rejections are silent (no toast, no row change).
  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
      const pending = [...aborts.values()]
      aborts.clear()
      pending.forEach((controller) => controller.abort())
    })
  }

  return { begin, settle, isCancellable, cancel }
}
