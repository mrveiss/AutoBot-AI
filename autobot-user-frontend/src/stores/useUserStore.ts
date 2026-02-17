import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useUserStore')

export interface UserProfile {
  id: string
  username: string
  email?: string
  displayName: string
  avatar?: string
  role: 'admin' | 'user' | 'viewer'
  preferences: UserPreferences
  createdAt: Date
  lastLoginAt?: Date
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'auto'
  language: string
  timezone: string
  notifications: {
    email: boolean
    browser: boolean
    sound: boolean
  }
  ui: {
    sidebarCollapsed: boolean
    compactMode: boolean
    showTooltips: boolean
    animationsEnabled: boolean
  }
  accessibility: {
    highContrast: boolean
    reducedMotion: boolean
    fontSize: 'small' | 'medium' | 'large'
    keyboardNavigation: boolean
  }
  chat: {
    autoSave: boolean
    messageHistory: number
    typingIndicators: boolean
    timestamps: boolean
  }
}

export interface AuthState {
  isAuthenticated: boolean
  token?: string
  refreshToken?: string
  expiresAt?: Date
}

export const useUserStore = defineStore('user', () => {
  // State
  const authState = ref<AuthState>({
    isAuthenticated: false
  })

  const currentUser = ref<UserProfile | null>(null)

  const defaultPreferences: UserPreferences = {
    theme: 'auto',
    language: 'en',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    notifications: {
      email: true,
      browser: true,
      sound: false
    },
    ui: {
      sidebarCollapsed: false,
      compactMode: false,
      showTooltips: true,
      animationsEnabled: true
    },
    accessibility: {
      highContrast: false,
      reducedMotion: false,
      fontSize: 'medium',
      keyboardNavigation: false
    },
    chat: {
      autoSave: true,
      messageHistory: 100,
      typingIndicators: true,
      timestamps: true
    }
  }

  // Computed
  const isAuthenticated = computed(() => authState.value.isAuthenticated)

  const isAdmin = computed(() => currentUser.value?.role === 'admin')

  const preferences = computed(() => currentUser.value?.preferences || defaultPreferences)

  const theme = computed(() => {
    const userTheme = preferences.value.theme
    if (userTheme === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return userTheme
  })

  const isTokenExpired = computed(() => {
    if (!authState.value.expiresAt) return false
    return new Date() >= authState.value.expiresAt
  })

  // Actions
  function login(user: UserProfile, tokens: { token: string; refreshToken?: string; expiresIn?: number }) {
    currentUser.value = user
    authState.value = {
      isAuthenticated: true,
      token: tokens.token,
      refreshToken: tokens.refreshToken,
      expiresAt: tokens.expiresIn ? new Date(Date.now() + tokens.expiresIn * 1000) : undefined
    }

    // Update last login
    if (currentUser.value) {
      currentUser.value.lastLoginAt = new Date()
    }
  }

  function logout() {
    currentUser.value = null
    authState.value = {
      isAuthenticated: false
    }
  }

  function updateProfile(updates: Partial<UserProfile>) {
    if (currentUser.value) {
      currentUser.value = {
        ...currentUser.value,
        ...updates
      }
    }
  }

  function updatePreferences(updates: Partial<UserPreferences>) {
    if (currentUser.value) {
      currentUser.value.preferences = {
        ...currentUser.value.preferences,
        ...updates
      }
    }
  }

  function updateTheme(theme: 'light' | 'dark' | 'auto') {
    updatePreferences({ theme })
    applyTheme()
  }

  function updateLanguage(language: string) {
    updatePreferences({ language })
  }

  function updateTimezone(timezone: string) {
    updatePreferences({ timezone })
  }

  function updateNotificationSettings(notifications: Partial<UserPreferences['notifications']>) {
    updatePreferences({
      notifications: {
        ...preferences.value.notifications,
        ...notifications
      }
    })
  }

  function updateUISettings(ui: Partial<UserPreferences['ui']>) {
    updatePreferences({
      ui: {
        ...preferences.value.ui,
        ...ui
      }
    })
  }

  function updateAccessibilitySettings(accessibility: Partial<UserPreferences['accessibility']>) {
    updatePreferences({
      accessibility: {
        ...preferences.value.accessibility,
        ...accessibility
      }
    })
    applyAccessibilitySettings()
  }

  function updateChatSettings(chat: Partial<UserPreferences['chat']>) {
    updatePreferences({
      chat: {
        ...preferences.value.chat,
        ...chat
      }
    })
  }

  function refreshToken(newToken: string, expiresIn?: number) {
    // Issue #821: Basic validation - reject empty/malformed tokens
    if (!newToken || typeof newToken !== 'string' || newToken.trim().length === 0) {
      logger.warn('refreshToken called with invalid token, ignoring')
      return
    }
    authState.value.token = newToken
    authState.value.expiresAt = expiresIn ? new Date(Date.now() + expiresIn * 1000) : undefined
  }

  // Theme and accessibility helpers
  function applyTheme() {
    const currentTheme = theme.value
    const root = document.documentElement

    if (currentTheme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }

    // Update meta theme-color for mobile browsers
    const metaThemeColor = document.querySelector('meta[name="theme-color"]')
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', currentTheme === 'dark' ? '#1f2937' : '#ffffff')
    }
  }

  function applyAccessibilitySettings() {
    const root = document.documentElement
    const settings = preferences.value.accessibility

    // High contrast
    if (settings.highContrast) {
      root.classList.add('high-contrast')
    } else {
      root.classList.remove('high-contrast')
    }

    // Reduced motion
    if (settings.reducedMotion) {
      root.classList.add('reduced-motion')
    } else {
      root.classList.remove('reduced-motion')
    }

    // Font size
    root.classList.remove('font-small', 'font-medium', 'font-large')
    root.classList.add(`font-${settings.fontSize}`)

    // Keyboard navigation
    if (settings.keyboardNavigation) {
      root.classList.add('keyboard-navigation')
    } else {
      root.classList.remove('keyboard-navigation')
    }
  }

  // Initialize user session from storage
  function initializeFromStorage() {
    try {
      const storedAuth = localStorage.getItem('autobot_auth')
      const storedUser = localStorage.getItem('autobot_user')

      if (storedAuth && storedUser) {
        const auth = JSON.parse(storedAuth)
        const user = JSON.parse(storedUser)

        // Check if token is not expired
        if (!auth.expiresAt || new Date(auth.expiresAt) > new Date()) {
          authState.value = {
            ...auth,
            expiresAt: auth.expiresAt ? new Date(auth.expiresAt) : undefined
          }
          currentUser.value = {
            ...user,
            createdAt: new Date(user.createdAt),
            lastLoginAt: user.lastLoginAt ? new Date(user.lastLoginAt) : undefined
          }

          applyTheme()
          applyAccessibilitySettings()
        }
      }
    } catch (error) {
      logger.error('Failed to initialize user from storage:', error)
    }
  }

  // Persist user session to storage
  function persistToStorage() {
    try {
      if (authState.value.isAuthenticated && currentUser.value) {
        localStorage.setItem('autobot_auth', JSON.stringify(authState.value))
        localStorage.setItem('autobot_user', JSON.stringify(currentUser.value))
      } else {
        localStorage.removeItem('autobot_auth')
        localStorage.removeItem('autobot_user')
      }
    } catch (error) {
      logger.error('Failed to persist user to storage:', error)
    }
  }

  // Check auth status from backend (handles single_user mode auto-auth)
  async function checkAuthFromBackend(): Promise<boolean> {
    try {
      // Issue #869: Use absolute URL to backend, not relative (which hits frontend nginx)
      const backendUrl = import.meta.env.VITE_API_BASE_URL || 'https://172.16.168.20:8443'
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5s timeout

      const response = await fetch(`${backendUrl}/api/auth/me`, {
        signal: controller.signal,
        headers: {
          'Accept': 'application/json'
        }
      })
      clearTimeout(timeoutId)

      if (response.ok) {
        const data = await response.json()
        if (data.authenticated) {
          // Auto-login with data from backend
          const user: UserProfile = {
            id: data.username,  // Use username as ID for single_user mode
            username: data.username,
            email: data.email || '',
            displayName: data.username.charAt(0).toUpperCase() + data.username.slice(1),
            role: data.role as 'admin' | 'user' | 'viewer',
            preferences: defaultPreferences,
            createdAt: new Date(),
            lastLoginAt: new Date()
          }
          currentUser.value = user
          authState.value = {
            isAuthenticated: true,
            token: data.deployment_mode === 'single_user' ? 'single_user_mode' : undefined
          }
          logger.info('Auto-authenticated from backend:', data.deployment_mode)
          return true
        }
      }
      return false
    } catch (error) {
      // Silently fail on timeout/network errors (don't block login page)
      if (error instanceof Error && error.name === 'AbortError') {
        logger.debug('Backend auth check timed out (5s)')
      } else {
        logger.debug('Backend auth check failed:', error)
      }
      return false
    }
  }

  // Change user password
  async function changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<{ success: boolean; message: string }> {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      }

      // Add authorization header if we have a token
      if (authState.value.token && authState.value.token !== 'single_user_mode') {
        headers['Authorization'] = `Bearer ${authState.value.token}`
      }

      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      })

      const data = await response.json()

      if (!response.ok) {
        // Handle validation errors from Pydantic
        if (data.detail) {
          // Check if it's a validation error array
          if (Array.isArray(data.detail)) {
            const messages = data.detail.map((err: { msg?: string }) => err.msg || 'Validation error')
            return { success: false, message: messages.join('. ') }
          }
          return { success: false, message: data.detail }
        }
        return { success: false, message: 'Failed to change password' }
      }

      logger.info('Password changed successfully')
      return { success: true, message: data.message || 'Password changed successfully' }
    } catch (error) {
      logger.error('Failed to change password:', error)
      return { success: false, message: 'Network error. Please try again.' }
    }
  }

  return {
    // State
    authState,
    currentUser,

    // Computed
    isAuthenticated,
    isAdmin,
    preferences,
    theme,
    isTokenExpired,

    // Actions
    login,
    logout,
    updateProfile,
    updatePreferences,
    updateTheme,
    updateLanguage,
    updateTimezone,
    updateNotificationSettings,
    updateUISettings,
    updateAccessibilitySettings,
    updateChatSettings,
    refreshToken,
    applyTheme,
    applyAccessibilitySettings,
    initializeFromStorage,
    persistToStorage,
    checkAuthFromBackend,
    changePassword
  }
})
