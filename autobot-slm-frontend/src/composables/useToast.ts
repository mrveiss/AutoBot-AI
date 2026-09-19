// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Re-export shim — the implementation lives in `@autobot/ui` (#14907).
 *
 * `useToast` existed twice: here (93 lines) and in autobot-frontend (184
 * lines) — same public contract, two implementations that had drifted
 * independently. This app's copy was the trimmed one: `MAX_TOASTS=5` with
 * no Tier-C (persistent error) protection, so a burst of toasts could evict
 * an unread error. The kit's copy is the union of both — see its own doc
 * comment for the capability diff this consolidation preserved.
 *
 * Re-exported rather than migrating every call site so every straggler
 * import keeps resolving; what goes is the fork, not the callers. Both apps
 * already depend on `@autobot/ui` (`file:../libs/autobot-ui`), so this
 * resolves in each. Mirrors the `useVncControls` shim pattern (#12931).
 */
export {
  useToast,
  provideToast,
  MAX_TOASTS,
  TOAST_DURATIONS,
  TOAST_INJECT_KEY,
  type ToastType,
  type Toast,
  type UseToastReturn,
} from '@autobot/ui'