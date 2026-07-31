// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Authentication Store
 *
 * Manages user authentication state and JWT tokens.
 * Issue #576 - Added MFA support in Phase 5.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'

const logger = createLogger('AuthStore')

interface User {
  username: string
  isAdmin: boolean
}

/**
 * Token payload of `POST /api/auth/login`, `/api/auth/refresh` and
 * `/api/mfa/verify-login`, derived from the generated OpenAPI contract
 * (#13138). The hand-written copy omitted `token` — the SLM mirrors the JWT
 * under both `access_token` and `token` so a client written against the core
 * backend reads it too (autobot-slm-backend/models/schemas.py:31-48).
 */
type TokenResponse = components['schemas']['TokenResponse']

/**
 * MFA challenge branch of `POST /api/auth/login`, whose response model is the
 * union `TokenResponse | MfaChallengeResponse` (autobot-slm-backend/api/auth.py:81).
 * Modelled as the union rather than one flattened all-optional shape so the
 * `requires_mfa` branch is the only place `temp_token` is readable.
 */
type MfaChallengeResponse = components['schemas']['MfaChallengeResponse']

type LoginResponse = TokenResponse | MfaChallengeResponse

interface LogoutResponse {
  logout_url?: string | null
}

/**
 * Narrow the `/api/auth/login` union. Both members carry an
 * `additionalProperties` catch-all in the contract, so a structural check on
 * the discriminator is required rather than a bare `in` test.
 */
function isMfaChallenge(data: LoginResponse): data is MfaChallengeResponse {
  return data.requires_mfa === true && typeof data.temp_token === 'string'
}

const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  // Session-scoped storage: tokens are cleared when the browser tab closes
  const token = ref<string | null>(sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(
    (() => {
      const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY)
      return raw ? JSON.parse(raw) : null
    })()
  )
  const loading = ref(false)
  const error = ref<string | null>(null)

  const mfaPending = ref(false)
  const mfaTempToken = ref('')

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.isAdmin ?? false)

  function getApiUrl(): string {
    if (import.meta.env.DEV) {
      return ''
    }
    return import.meta.env.VITE_API_URL || ''
  }

  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${getApiUrl()}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Login failed')
      }

      const data: LoginResponse = await response.json()

      if (isMfaChallenge(data)) {
        mfaPending.value = true
        mfaTempToken.value = data.temp_token
        return false
      }

      token.value = data.access_token
      sessionStorage.setItem(TOKEN_KEY, data.access_token)

      await fetchCurrentUser()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      return false
    } finally {
      loading.value = false
    }
  }

  async function completeMFALogin(code: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      // `temp_token` is a QUERY parameter, not a body field: the backend
      // declares it as a bare `str` argument beside the Pydantic body model
      // (autobot-slm-backend/api/mfa.py:96-99), which FastAPI binds from the
      // query string. The generated contract confirms it under
      // `parameters.query`. Sending it in the body 422s on the missing
      // required query parameter, blocking MFA login entirely (#12420).
      const query = new URLSearchParams({ temp_token: mfaTempToken.value })
      const response = await fetch(
        `${getApiUrl()}/api/mfa/verify-login?${query.toString()}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code }),
        }
      )
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'MFA verification failed')
      }
      const data: TokenResponse = await response.json()
      token.value = data.access_token
      sessionStorage.setItem(TOKEN_KEY, data.access_token)
      mfaPending.value = false
      mfaTempToken.value = ''
      await fetchCurrentUser()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'MFA verification failed'
      return false
    } finally {
      loading.value = false
    }
  }

  function resetMFA(): void {
    mfaPending.value = false
    mfaTempToken.value = ''
    error.value = null
  }

  async function fetchCurrentUser(): Promise<void> {
    if (!token.value) return

    try {
      const response = await fetch(`${getApiUrl()}/api/auth/me`, {
        headers: {
          Authorization: `Bearer ${token.value}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to fetch user')
      }

      const data = await response.json()
      user.value = {
        username: data.username,
        isAdmin: data.is_admin,
      }
      sessionStorage.setItem(USER_KEY, JSON.stringify(user.value))
    } catch {
      logout()
    }
  }

  async function refreshToken(): Promise<boolean> {
    if (!token.value) return false

    try {
      const response = await fetch(`${getApiUrl()}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.value}`,
        },
      })

      if (!response.ok) {
        throw new Error('Token refresh failed')
      }

      const data: TokenResponse = await response.json()
      token.value = data.access_token
      sessionStorage.setItem(TOKEN_KEY, data.access_token)
      return true
    } catch {
      logout()
      return false
    }
  }

  /**
   * Revoke the current token server-side, then clear local session.
   *
   * The backend revokes the JWT jti and (for SSO sessions) returns an IdP
   * end_session URL. Logout must never get stuck: if the revoke call fails the
   * local session is still cleared and the user is redirected.
   */
  async function logout(): Promise<void> {
    const currentToken = token.value
    let logoutUrl: string | null = null

    if (currentToken) {
      try {
        const response = await fetch(`${getApiUrl()}/api/auth/logout`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${currentToken}`,
          },
        })
        if (response.ok) {
          const data: LogoutResponse = await response.json()
          logoutUrl = data.logout_url ?? null
        } else {
          logger.warn('Backend logout returned non-OK status', response.status)
        }
      } catch (e) {
        logger.warn('Backend logout call failed; clearing session locally', e)
      }
    }

    token.value = null
    user.value = null
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_KEY)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)

    if (logoutUrl) {
      // RP-initiated logout: end the IdP session too
      window.location.assign(logoutUrl)
    } else {
      router.push('/login')
    }
  }

  function getAuthHeaders(): Record<string, string> {
    if (!token.value) return {}
    return {
      Authorization: `Bearer ${token.value}`,
    }
  }

  async function checkAuth(): Promise<boolean> {
    if (!token.value) return false

    try {
      await fetchCurrentUser()
      return !!user.value
    } catch {
      return false
    }
  }

  return {
    token,
    user,
    loading,
    error,
    mfaPending,
    mfaTempToken,
    isAuthenticated,
    isAdmin,
    login,
    completeMFALogin,
    resetMFA,
    logout,
    refreshToken,
    fetchCurrentUser,
    getAuthHeaders,
    checkAuth,
    getApiUrl,
  }
})
