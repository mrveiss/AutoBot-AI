// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Canonical reader for the persisted JWT auth token (#10861).
 *
 * AutoBot always runs full user management with backend auth enabled (#10713);
 * there is no `single_user` deployment mode. Older deployments could persist a
 * synthetic `single_user_mode` marker in place of a real JWT. That marker is no
 * longer produced, but it may still linger in a browser's localStorage — sending
 * it as a Bearer to an auth-enabled backend yields 401s. This helper is the one
 * place that reads the stored token, rejecting the legacy marker so stale
 * storage cannot leak a fake token into requests.
 */

/** localStorage key holding the serialized auth state. */
const AUTH_STORAGE_KEY = 'autobot_auth'

/**
 * Legacy synthetic token used by the retired `single_user` deployment mode.
 * Never emitted anymore; still rejected on read to purge stale storage.
 */
const LEGACY_SINGLE_USER_TOKEN = 'single_user_mode'

/** True when the value is a usable JWT (present and not the legacy marker). */
export function isRealAuthToken(token: unknown): token is string {
  return typeof token === 'string' && token.length > 0 && token !== LEGACY_SINGLE_USER_TOKEN
}

/**
 * Read the persisted JWT from localStorage. Returns null when absent, malformed,
 * or when only the legacy `single_user_mode` marker is stored. Callers must
 * handle the null case (defer the request / omit the Authorization header).
 */
export function readStoredAuthToken(): string | null {
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!stored) return null
    const auth: { token?: unknown } = JSON.parse(stored)
    return isRealAuthToken(auth.token) ? auth.token : null
  } catch {
    return null
  }
}
