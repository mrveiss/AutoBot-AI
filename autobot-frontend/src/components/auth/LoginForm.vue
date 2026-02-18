<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="logo">
          <h1>AutoBot</h1>
          <p class="subtitle">Secure Access Portal</p>
        </div>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username" class="form-label">Username</label>
          <input
            id="username"
            v-model="credentials.username"
            type="text"
            class="form-input"
            :class="{ 'error': validationErrors.username }"
            placeholder="Enter your username"
            required
            autocomplete="username"
            :disabled="isLoading"
          />
          <div v-if="validationErrors.username" class="error-message">
            {{ validationErrors.username }}
          </div>
        </div>

        <div class="form-group">
          <label for="password" class="form-label">Password</label>
          <div class="password-input-wrapper">
            <input
              id="password"
              v-model="credentials.password"
              :type="showPassword ? 'text' : 'password'"
              class="form-input"
              :class="{ 'error': validationErrors.password }"
              placeholder="Enter your password"
              required
              autocomplete="current-password"
              :disabled="isLoading"
            />
            <button
              type="button"
              class="password-toggle"
              @click="showPassword = !showPassword"
              :disabled="isLoading"
            >
              <i :class="showPassword ? 'icon-eye-off' : 'icon-eye'"></i>
            </button>
          </div>
          <div v-if="validationErrors.password" class="error-message">
            {{ validationErrors.password }}
          </div>
        </div>

        <BaseAlert
          v-if="loginError"
          variant="error"
          :message="loginError"
        />

        <BaseAlert
          v-if="lockoutMessage"
          variant="warning"
          :message="lockoutMessage"
        />

        <button
          type="submit"
          class="login-button"
          :disabled="isLoading || !isFormValid"
        >
          <span v-if="isLoading" class="loading-spinner"></span>
          <span v-else>Sign In</span>
        </button>

      </form>
    </div>

    <div class="login-footer">
      <p>AutoBot Security Portal - Authenticated Access Required</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useRouter } from 'vue-router'

const logger = createLogger('LoginForm')
import { useUserStore, type UserProfile } from '@/stores/useUserStore'
import ApiClient from '@/utils/ApiClient'
import BaseAlert from '@/components/ui/BaseAlert.vue'

const router = useRouter()
const userStore = useUserStore()

// Reactive state
const credentials = reactive({
  username: '',
  password: ''
})

const isLoading = ref(false)
const showPassword = ref(false)
const loginError = ref('')
const lockoutMessage = ref('')
const validationErrors = reactive({
  username: '',
  password: ''
})

// Computed properties
const isFormValid = computed(() => {
  return credentials.username.length >= 2 &&
         credentials.password.length >= 1 &&
         !validationErrors.username &&
         !validationErrors.password
})

// Validation functions
function validateUsername() {
  validationErrors.username = ''

  if (!credentials.username) {
    validationErrors.username = 'Username is required'
    return false
  }

  if (credentials.username.length < 2) {
    validationErrors.username = 'Username must be at least 2 characters'
    return false
  }

  if (credentials.username.length > 50) {
    validationErrors.username = 'Username is too long'
    return false
  }

  // Basic sanitization check
  const validPattern = /^[a-zA-Z0-9_\-.]+$/
  if (!validPattern.test(credentials.username)) {
    validationErrors.username = 'Username contains invalid characters'
    return false
  }

  return true
}

function validatePassword() {
  validationErrors.password = ''

  if (!credentials.password) {
    validationErrors.password = 'Password is required'
    return false
  }

  if (credentials.password.length > 128) {
    validationErrors.password = 'Password is too long'
    return false
  }

  return true
}

// Authentication handler
async function handleLogin() {
  // Clear previous errors
  loginError.value = ''
  lockoutMessage.value = ''

  // Validate form
  const isUsernameValid = validateUsername()
  const isPasswordValid = validatePassword()

  if (!isUsernameValid || !isPasswordValid) {
    return
  }

  isLoading.value = true

  try {
    // ApiClient.post() returns parsed JSON directly (#810)
    const response = await ApiClient.post('/api/auth/login', {
      username: credentials.username,
      password: credentials.password
    })

    if (response.success && response.user && response.token) {
      // Map backend response to complete UserProfile (#946)
      const u = response.user
      const userProfile: UserProfile = {
        id: u.user_id || u.username || '',
        username: u.username,
        email: u.email || '',
        displayName: u.username
          ? u.username.charAt(0).toUpperCase() + u.username.slice(1)
          : u.username,
        role: (u.role as 'admin' | 'user' | 'viewer') || 'user',
        preferences: {
          theme: 'auto',
          language: 'en',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          notifications: { email: true, browser: true, sound: false },
          ui: { sidebarCollapsed: false, compactMode: false, showTooltips: true, animationsEnabled: true },
          accessibility: { highContrast: false, reducedMotion: false, fontSize: 'medium', keyboardNavigation: false },
          chat: { autoSave: true, messageHistory: 100, typingIndicators: true, timestamps: true }
        },
        createdAt: new Date(),
        lastLoginAt: new Date()
      }
      // Store authentication data
      userStore.login(userProfile, {
        token: response.token,
        expiresIn: 24 * 60 * 60 // 24 hours in seconds
      })

      // Persist to localStorage
      userStore.persistToStorage()

      // Clear form
      credentials.username = ''
      credentials.password = ''

      // Redirect to intended route or chat
      const redirectTo = router.currentRoute.value.query.redirect as string || '/chat'
      await router.push(redirectTo)

    } else {
      loginError.value = response.message || 'Login failed. Please check your credentials.'
    }

  } catch (error: any) {
    logger.error('Login error:', error)

    // ApiClient throws Error with message like "HTTP 401: Invalid username or password"
    const statusMatch = error.message?.match(/HTTP (\d+)/)
    const status = statusMatch ? parseInt(statusMatch[1]) : 0
    if (status === 401) {
      loginError.value = 'Invalid username or password'
    } else if (status === 423) {
      lockoutMessage.value = 'Account temporarily locked due to multiple failed attempts'
    } else if (status === 429) {
      loginError.value = 'Too many login attempts. Please try again later.'
    } else if (status >= 500) {
      loginError.value = 'Server error. Please try again later.'
    } else {
      loginError.value = error.message || 'An unexpected error occurred'
    }
  } finally {
    isLoading.value = false
  }
}

// Check authentication status on mount
onMounted(async () => {
  // If already authenticated, redirect to chat
  if (userStore.isAuthenticated) {
    await router.push('/chat')
    return
  }

  // Try to restore session from storage
  userStore.initializeFromStorage()

  if (userStore.isAuthenticated) {
    await router.push('/chat')
  }
})
</script>

<style scoped>
/**
 * LoginForm.vue - Migrated to Design Tokens
 * Issue #704: CSS Design System - Centralized Theming
 *
 * Hardcoded colors replaced with CSS variables from design-tokens.css
 */

.login-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: var(--spacing-4);
}

.login-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  padding: var(--spacing-8);
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: var(--spacing-8);
}

.logo h1 {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin: 0;
}

.subtitle {
  color: var(--text-secondary);
  margin: var(--spacing-2) 0 0 0;
  font-size: var(--text-sm);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-label {
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.form-input {
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out),
              box-shadow var(--duration-200) var(--ease-in-out);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-input.error {
  border-color: var(--color-error);
}

.form-input:disabled {
  background-color: var(--bg-tertiary);
  cursor: not-allowed;
  opacity: 0.6;
}

.form-input::placeholder {
  color: var(--text-muted);
}

.password-input-wrapper {
  position: relative;
}

.password-toggle {
  position: absolute;
  right: var(--spacing-3);
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0;
  font-size: var(--text-lg);
  transition: color var(--duration-150) var(--ease-in-out);
}

.password-toggle:hover {
  color: var(--text-primary);
}

.password-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.error-message {
  color: var(--color-error);
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}


.login-button {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-3-5);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.login-button:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.login-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.loading-spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid transparent;
  border-top: 2px solid currentColor;
  border-radius: var(--radius-full);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-footer {
  margin-top: var(--spacing-8);
  text-align: center;
}

.login-footer p {
  color: var(--text-on-primary);
  opacity: 0.8;
  font-size: var(--text-sm);
  margin: 0;
}

/* Icon classes for basic icons */
.icon-eye::before { content: '👁'; }
.icon-eye-off::before { content: '🙈'; }

/* Dark mode support - now handled by design tokens */
/* The design tokens already define dark theme colors as defaults */

/* Responsive design */
@media (max-width: 480px) {
  .login-container {
    padding: var(--spacing-2);
  }

  .login-card {
    padding: var(--spacing-6);
  }

  .logo h1 {
    font-size: var(--text-2xl);
  }
}
</style>
