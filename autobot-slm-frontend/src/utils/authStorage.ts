// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SLM session storage -- the one place that knows the keys (#17856 row 8).
 *
 * The token lives in sessionStorage (cleared when the tab closes); a
 * localStorage copy from older builds is still read so an upgrade does not
 * sign anyone out. stores/auth.ts is the only writer: views hand a new token
 * to `authStore.adoptToken()`, never to storage directly. Leaf module -- no
 * store or client imports, so ApiClient and the store can both use it.
 */

export const SLM_TOKEN_KEY = 'slm_access_token'
export const SLM_USER_KEY = 'slm_user'

/** Read one session key, preferring sessionStorage. Null when absent or storage is unavailable. */
function readKey(key: string): string | null {
  try {
    return sessionStorage.getItem(key) || localStorage.getItem(key)
  } catch {
    return null
  }
}

/** The stored SLM bearer token, or null. */
export function readSlmToken(): string | null {
  return readKey(SLM_TOKEN_KEY)
}

/** The stored SLM user record (raw JSON), or null. */
export function readSlmUserRaw(): string | null {
  return readKey(SLM_USER_KEY)
}

/** Persist a token for this tab. Called by stores/auth.ts only. */
export function writeSlmToken(token: string): void {
  sessionStorage.setItem(SLM_TOKEN_KEY, token)
}

/** Persist the user record for this tab. Called by stores/auth.ts only. */
export function writeSlmUser(raw: string): void {
  sessionStorage.setItem(SLM_USER_KEY, raw)
}

/** Remove the session from both storages (logout or a rejected token). */
export function clearSlmSession(): void {
  try {
    for (const key of [SLM_TOKEN_KEY, SLM_USER_KEY]) {
      sessionStorage.removeItem(key)
      localStorage.removeItem(key)
    }
  } catch {
    /* storage unavailable -- nothing to clear */
  }
}
