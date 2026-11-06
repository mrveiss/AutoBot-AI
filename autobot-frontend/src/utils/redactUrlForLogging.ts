// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Re-export shim -- the one implementation lives in `@autobot/ui` (#18550).
 *
 * `@autobot/terminal` used to carry a second copy, held in sync by a drift
 * test (#15002). Both now import the kit's, so there is nothing to drift.
 * Kept so this app's importers keep resolving; what moved is the
 * implementation, not the callers.
 */
export { redactUrlForLogging, redactErrorForLogging } from '@autobot/ui'
