/**
 * Re-export shim — the implementation lives in `@autobot/ui` (#14907).
 *
 * `useToast` existed twice: here (184 lines) and in autobot-slm-frontend (93
 * lines) — same public contract, two implementations that had drifted
 * independently (`MAX_TOASTS`, Tier-C persistent-error handling, overflow
 * queueing). The kit's copy is the union of both — see its own doc comment
 * for the capability diff this consolidation preserved.
 *
 * Re-exported rather than migrating every call site so every straggler
 * import (and every `vi.mock('@/composables/useToast', ...)` in this app's
 * tests) keeps resolving; what goes is the fork, not the callers. Both apps
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
