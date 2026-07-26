// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared "logout on 401" guard for auth-flow endpoints (#12654).
 *
 * The canonical `slmApiClient` intentionally skips its session-clearing 401
 * handler for `/auth/**` and `/mfa/**` endpoints (a 401 there is a credential
 * failure, not a rejected session). Both `useMfaApi` and `useSsoApi` historically
 * logged the user out on ANY 401 via their axios response interceptor, so each
 * wrapped those calls in a byte-identical `withAuthGuard`. This consolidates that
 * helper: pass the auth store's `logout` and receive the same guard.
 */

/**
 * Wrap a composable's auth-flow call so a `HTTP 401` rejection triggers `logout`
 * (preserving the historic interceptor behaviour) before re-throwing unchanged.
 */
export function createAuthGuard(logout: () => void) {
  return async function withAuthGuard<T>(op: () => Promise<T>): Promise<T> {
    try {
      return await op()
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('HTTP 401')) {
        logout()
      }
      throw error
    }
  }
}
