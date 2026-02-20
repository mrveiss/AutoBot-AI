<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LoginView - Authentication page
 *
 * Issue #754: Added ARIA labels, roles, aria-live for errors,
 * accessible password toggle, and MFA form accessibility.
 */

import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSsoApi, type ActiveProvider } from '@/composables/useSsoApi'

const router = useRouter()
const authStore = useAuthStore()

const ssoApi = useSsoApi()

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const ssoProviders = ref<ActiveProvider[]>([])
const ssoLoading = ref(false)
const ssoError = ref<string | null>(null)
const mfaCode = ref('')

async function handleLogin(): Promise<void> {
  const success = await authStore.login(username.value, password.value)
  if (success) {
    router.push('/')
  }
}

async function handleMFAVerify(): Promise<void> {
  const success = await authStore.completeMFALogin(mfaCode.value)
  if (success) {
    router.push('/')
  }
}

function cancelMFA(): void {
  authStore.resetMFA()
  mfaCode.value = ''
}

async function handleSSOLogin(provider: ActiveProvider): Promise<void> {
  ssoLoading.value = true
  ssoError.value = null
  try {
    if (provider.provider_type === 'ldap' || provider.provider_type === 'active_directory') {
      const response = await ssoApi.loginWithLDAP(provider.id, username.value, password.value)
      localStorage.setItem('slm_access_token', response.access_token)
      await authStore.checkAuth()
      router.push('/')
    } else {
      const response = await ssoApi.initiateSSOLogin(provider.id)
      window.location.href = response.redirect_url
    }
  } catch {
    ssoError.value = 'SSO login failed. Please try again.'
  } finally {
    ssoLoading.value = false
  }
}

onMounted(async () => {
  try {
    ssoProviders.value = await ssoApi.getActiveProviders()
  } catch {
    // SSO providers not available
  }
})
</script>

<template>
  <main
    id="main-content"
    class="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4"
    aria-label="Login page"
  >
    <div class="w-full max-w-md">
      <!-- Logo/Header -->
      <div class="text-center mb-8">
        <div
          class="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg mb-4"
          aria-hidden="true"
        >
          <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-white">Service Lifecycle Manager</h1>
        <p class="text-slate-400 mt-1">Sign in to your admin account</p>
      </div>

      <!-- Login Form -->
      <div class="bg-white rounded-2xl shadow-xl p-8">
        <!-- Standard Login Form -->
        <form
          v-if="!authStore.mfaPending"
          @submit.prevent="handleLogin"
          class="space-y-6"
          aria-label="Sign in form"
        >
          <!-- Username -->
          <div>
            <label for="username" class="block text-sm font-medium text-gray-700 mb-1">
              Username
            </label>
            <div class="relative">
              <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" aria-hidden="true">
                <svg class="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <input
                id="username"
                v-model="username"
                type="text"
                required
                autocomplete="username"
                aria-required="true"
                class="block w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 transition-colors"
                placeholder="Enter your username"
              />
            </div>
          </div>

          <!-- Password -->
          <div>
            <label for="password" class="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <div class="relative">
              <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" aria-hidden="true">
                <svg class="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <input
                id="password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                required
                autocomplete="current-password"
                aria-required="true"
                class="block w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                placeholder="Enter your password"
              />
              <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute inset-y-0 right-0 pr-3 flex items-center"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
                :aria-pressed="showPassword"
              >
                <svg v-if="showPassword" class="h-5 w-5 text-gray-400 hover:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
                <svg v-else class="h-5 w-5 text-gray-400 hover:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Error Message -->
          <div v-if="authStore.error" class="bg-red-50 border border-red-200 rounded-lg p-3" role="alert">
            <div class="flex items-center gap-2 text-red-700">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span class="text-sm">{{ authStore.error }}</span>
            </div>
          </div>

          <!-- Submit Button -->
          <button
            type="submit"
            :disabled="authStore.loading"
            class="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-gradient-to-r from-primary-600 to-primary-700 text-white font-medium rounded-lg hover:from-primary-700 hover:to-primary-800 focus:ring-4 focus:ring-primary-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg v-if="authStore.loading" class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span>{{ authStore.loading ? 'Signing in...' : 'Sign in' }}</span>
          </button>
        </form>

        <!-- MFA Verification Form -->
        <div v-else class="space-y-6" role="form" aria-label="Two-factor authentication">
          <div class="text-center mb-4">
            <svg class="w-12 h-12 text-primary-600 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <h2 class="text-lg font-semibold text-gray-900">Two-Factor Authentication</h2>
            <p class="text-sm text-gray-500">Enter the code from your authenticator app</p>
          </div>

          <div>
            <label for="mfa-code" class="sr-only">Authentication code</label>
            <input
              id="mfa-code"
              v-model="mfaCode"
              type="text"
              inputmode="numeric"
              maxlength="8"
              autocomplete="one-time-code"
              aria-label="6-digit authentication code"
              class="block w-full text-center text-2xl tracking-widest py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="000000"
              @keyup.enter="handleMFAVerify"
            />
          </div>

          <div v-if="authStore.error" class="bg-red-50 border border-red-200 rounded-lg p-3" role="alert">
            <span class="text-sm text-red-700">{{ authStore.error }}</span>
          </div>

          <button
            @click="handleMFAVerify"
            :disabled="authStore.loading || mfaCode.length < 6"
            class="w-full py-2.5 px-4 bg-gradient-to-r from-primary-600 to-primary-700 text-white font-medium rounded-lg hover:from-primary-700 hover:to-primary-800 disabled:opacity-50"
          >
            {{ authStore.loading ? 'Verifying...' : 'Verify' }}
          </button>

          <button
            @click="cancelMFA"
            type="button"
            class="w-full py-2 text-sm text-gray-500 hover:text-gray-700"
          >
            Back to login
          </button>
        </div>

        <!-- SSO Login Options -->
        <div v-if="ssoProviders.length > 0 && !authStore.mfaPending" class="mt-6">
          <div class="relative my-6" aria-hidden="true">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-gray-300"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-3 bg-white text-gray-400">Or continue with</span>
            </div>
          </div>

          <div class="space-y-3" role="group" aria-label="Single sign-on providers">
            <button
              v-for="provider in ssoProviders"
              :key="provider.id"
              @click="handleSSOLogin(provider)"
              :disabled="ssoLoading"
              type="button"
              class="w-full flex items-center justify-center gap-3 px-4 py-2.5 bg-gray-50 border border-gray-300 rounded-lg hover:bg-gray-100 text-gray-700 transition-colors disabled:opacity-50"
              :aria-label="`Sign in with ${provider.name}`"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              <span class="text-sm font-medium">{{ provider.name }}</span>
            </button>
          </div>

          <p v-if="ssoError" class="mt-3 text-sm text-red-500 text-center" role="alert">{{ ssoError }}</p>
        </div>

        <!-- Footer -->
        <div class="mt-6 pt-6 border-t border-gray-200">
          <p class="text-center text-sm text-gray-500">
            AutoBot Service Lifecycle Manager
          </p>
        </div>
      </div>

    </div>
  </main>
</template>
