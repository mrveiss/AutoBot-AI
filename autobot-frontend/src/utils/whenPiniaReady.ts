// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { getActivePinia } from 'pinia'

/**
 * Run `callback` once Pinia is installed (#9693).
 *
 * Module-level singleton services (LiveEventService, GlobalWebSocketService)
 * auto-connect via a delayed timer that reads the user store. If that timer
 * fires before `app.use(pinia)` has run (slow app mount) — or after the Pinia
 * instance is gone (test teardown, HMR dispose) — `useUserStore()` throws an
 * uncaught "no active Pinia" error. Instead of assuming a fixed delay is
 * always long enough, poll until a Pinia instance is actually active.
 */
export function whenPiniaReady(callback: () => void, delayMs = 1000): void {
  setTimeout(() => {
    if (getActivePinia()) {
      callback()
    } else {
      whenPiniaReady(callback, delayMs)
    }
  }, delayMs)
}
