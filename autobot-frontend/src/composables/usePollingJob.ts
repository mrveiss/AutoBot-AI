// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Re-export shim — the implementation lives in `@autobot/ui` (#19482).
 *
 * Kept so the app's 32 importers, and every `vi.mock('@/composables/usePollingJob', ...)`
 * in its tests, keep resolving; what moved is the implementation, not the
 * callers. Mirrors the `useToast` shim (#14907).
 */
export { usePollingJob, type UsePollingJobOptions, type UsePollingJobReturn } from '@autobot/ui'
