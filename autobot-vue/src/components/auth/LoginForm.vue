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

        <div v-if="loginError" class="error-alert">
          <i class="icon-alert-circle"></i>
          {{ loginError }}
        </div>

        <div v-if="lockoutMessage" class="warning-alert">
          <i class="icon-lock"></i>
          {{ lockoutMessage }}
        </div>

        <button
          type="submit"
          class="login-button"
          :disabled="isLoading || !isFormValid"
        >
          <span v-if="isLoading" class="loading-spinner"></span>
          <span v-else>Sign In</span>
        </button>

        <div class="login-info">
          <p class="demo-credentials">
            <strong>Demo Credentials:</strong><br>
            Admin: admin / autobotadmin123<br>
            Developer: developer / dev123secure<br>
            Read-only: readonly / readonly123
          </p>
        </div>
      </form>
    </div>

    <div class="login-footer">
      <p>AutoBot Security Portal - Authenticated Access Required</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/useUserStore'
import { ApiClient } from '@/utils/ApiClient'

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
    // Call login API
    const response = await ApiClient.post('/api/auth/login', {
      username: credentials.username,
      password: credentials.password
    })

    if (response.success && response.user && response.token) {
      // Store authentication data
      userStore.login(response.user, {
        token: response.token,
        refreshToken: response.refreshToken,
        expiresIn: 24 * 60 * 60 // 24 hours in seconds
      })

      // Persist to localStorage
      userStore.persistToStorage()

      // Clear form
      credentials.username = ''
      credentials.password = ''

      // Redirect to dashboard or intended route
      const redirectTo = router.currentRoute.value.query.redirect as string || '/dashboard'
      await router.push(redirectTo)

    } else {
      loginError.value = response.message || 'Login failed. Please check your credentials.'
    }

  } catch (error: any) {
    console.error('Login error:', error)

    if (error.status === 401) {
      loginError.value = 'Invalid username or password'
    } else if (error.status === 423) {
      lockoutMessage.value = 'Account temporarily locked due to multiple failed attempts'
    } else if (error.status === 429) {
      loginError.value = 'Too many login attempts. Please try again later.'
    } else if (error.status >= 500) {
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
  // If already authenticated, redirect to dashboard
  if (userStore.isAuthenticated) {
    await router.push('/dashboard')
    return
  }

  // Try to restore session from storage
  userStore.initializeFromStorage()

  if (userStore.isAuthenticated) {
    await router.push('/dashboard')
  }
})
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 1rem;
}

.login-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  padding: 2rem;
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.logo h1 {
  font-size: 2rem;
  font-weight: bold;
  color: #1f2937;
  margin: 0;
}

.subtitle {
  color: #6b7280;
  margin: 0.5rem 0 0 0;
  font-size: 0.875rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-weight: 500;
  color: #374151;
  font-size: 0.875rem;
}

.form-input {
  padding: 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 1rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input.error {
  border-color: #ef4444;
}

.form-input:disabled {
  background-color: #f9fafb;
  cursor: not-allowed;
}

.password-input-wrapper {
  position: relative;
}

.password-toggle {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 0;
  font-size: 1.125rem;
}

.password-toggle:hover {
  color: #374151;
}

.password-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.error-message {
  color: #ef4444;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.error-alert, .warning-alert {
  padding: 0.75rem;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.error-alert {
  background-color: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
}

.warning-alert {
  background-color: #fffbeb;
  color: #d97706;
  border: 1px solid #fed7aa;
}

.login-button {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  padding: 0.875rem;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.login-button:hover:not(:disabled) {
  transform: translateY(-1px);
  opacity: 0.9;
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
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-info {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e5e7eb;
}

.demo-credentials {
  font-size: 0.75rem;
  color: #6b7280;
  line-height: 1.4;
  margin: 0;
  text-align: center;
}

.login-footer {
  margin-top: 2rem;
  text-align: center;
}

.login-footer p {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.875rem;
  margin: 0;
}

/* Icon classes for basic icons */
.icon-eye::before { content: '👁'; }
.icon-eye-off::before { content: '🙈'; }
.icon-alert-circle::before { content: '⚠️'; }
.icon-lock::before { content: '🔒'; }

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .login-card {
    background: #1f2937;
    color: white;
  }

  .logo h1 {
    color: white;
  }

  .form-label {
    color: #e5e7eb;
  }

  .form-input {
    background: #374151;
    border-color: #4b5563;
    color: white;
  }

  .form-input:focus {
    border-color: #667eea;
  }

  .form-input:disabled {
    background-color: #374151;
  }
}

/* Responsive design */
@media (max-width: 480px) {
  .login-container {
    padding: 0.5rem;
  }

  .login-card {
    padding: 1.5rem;
  }

  .logo h1 {
    font-size: 1.75rem;
  }
}
</style>