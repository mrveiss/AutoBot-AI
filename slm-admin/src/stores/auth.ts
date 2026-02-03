// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Authentication Store
 *
 * Manages user authentication state and JWT tokens.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

interface User {
  username: string
  isAdmin: boolean
}

interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()

  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(
    localStorage.getItem(USER_KEY)
      ? JSON.parse(localStorage.getItem(USER_KEY)!)
      : null
  )
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.isAdmin ?? false)

  function getApiUrl(): string {
    // Use relative URLs in development (Vite proxy handles /api)
    // Use env variable in production builds
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

      const data: TokenResponse = await response.json()
      token.value = data.access_token
      localStorage.setItem(TOKEN_KEY, data.access_token)

      await fetchCurrentUser()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      return false
    } finally {
      loading.value = false
    }
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
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
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
      localStorage.setItem(TOKEN_KEY, data.access_token)
      return true
    } catch {
      logout()
      return false
    }
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    router.push('/login')
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
    isAuthenticated,
    isAdmin,
    login,
    logout,
    refreshToken,
    fetchCurrentUser,
    getAuthHeaders,
    checkAuth,
    getApiUrl,
  }
})
