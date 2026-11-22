// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useStatusMessage Composable
 *
 * The one transient status line for the knowledge maintenance panels (backup, cleanup,
 * memory and session orphans), rendered through the kit BaseAlert. Each panel used to
 * carry its own copy of this state, an icon map and the banner markup (#19669).
 */

import { computed, ref } from 'vue'
import type { ToastType } from '@autobot/ui'

/** A success line clears itself after this long; other types stay until dismissed. */
export const STATUS_SUCCESS_DISMISS_MS = 5000

export interface StatusMessage {
  /** Changes on every show, so a repeated message restarts the alert's timer. */
  id: number
  type: ToastType
  text: string
}

export function useStatusMessage() {
  const statusMessage = ref<StatusMessage | null>(null)
  let nextId = 0

  function showStatus(type: ToastType, text: string): void {
    statusMessage.value = { id: ++nextId, type, text }
  }

  function clearStatus(): void {
    statusMessage.value = null
  }

  /** BaseAlert `auto-dismiss` for the current line: 0 keeps it. */
  const statusAutoDismiss = computed(() =>
    statusMessage.value?.type === 'success' ? STATUS_SUCCESS_DISMISS_MS : 0,
  )

  return { statusMessage, showStatus, clearStatus, statusAutoDismiss }
}
