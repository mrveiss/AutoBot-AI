// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useBodyScrollLock Composable (#5422)
 *
 * Fourth primitive in the dialog-a11y set (with useFocusTrap #5130,
 * useFocusRestore #5356, useInitialFocus #5411). Locks `document.body`
 * scroll while "active" is true, unlocks when it becomes false.
 *
 * Reference-counted across all consumers — when two modals are stacked,
 * closing the inner leaves the lock active until the outer also closes.
 * This is the bug the original BaseModal implementation couldn't prevent
 * because it toggled overflow unconditionally.
 *
 * Implementation note: we preserve the pre-lock value of
 * `document.body.style.overflow` (captured once, the first time the
 * counter goes from 0 → 1). If some other subsystem has already set
 * overflow (e.g. a Vue Router transition), we restore to that value on
 * full unlock, not to ''.
 */

import { watch, onUnmounted, type Ref } from 'vue'

/**
 * Module-level reference count and saved-overflow value. Shared across
 * all calls to `useBodyScrollLock` so stacked modals compose correctly.
 */
let lockCount = 0
let savedOverflow = ''

function acquire(): void {
  if (lockCount === 0) {
    savedOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  lockCount++
}

function release(): void {
  if (lockCount === 0) return
  lockCount--
  if (lockCount === 0) {
    document.body.style.overflow = savedOverflow
    savedOverflow = ''
  }
}

/**
 * @param activeWhen  Ref that is true while the consumer wants body
 *                    scroll locked. Fires on every false→true /
 *                    true→false transition plus initial evaluation so
 *                    components mounted with activeWhen=true lock
 *                    immediately.
 */
export function useBodyScrollLock(activeWhen: Ref<boolean>): void {
  // Track whether this consumer currently holds the lock, so unmount-
  // while-active correctly releases without double-releasing on the
  // subsequent watch callback (which won't fire after unmount anyway).
  let held = false

  watch(
    activeWhen,
    (active, wasActive) => {
      if (active && !wasActive) {
        acquire()
        held = true
      } else if (!active && wasActive) {
        release()
        held = false
      }
    },
    { immediate: true }
  )

  onUnmounted(() => {
    if (held) {
      release()
      held = false
    }
  })
}

/**
 * Test-only: reset the module-level state. Used by unit tests to ensure
 * a clean counter between cases. Not exported from the public surface.
 */
export function __resetLockStateForTests(): void {
  lockCount = 0
  savedOverflow = ''
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
}
