// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { ref, onScopeDispose } from 'vue'
import type { Ref } from 'vue'

export interface TransientError {
  message: Ref<string | null>
  show(msg: string): void
  clear(): void
}

export function useTransientError(ttlMs = 5000): TransientError {
  const message = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null

  function clear() {
    message.value = null
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function show(msg: string) {
    if (timer !== null) clearTimeout(timer)
    message.value = msg
    timer = setTimeout(clear, ttlMs)
  }

  onScopeDispose(clear)

  return { message, show, clear }
}
