// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * SSOCallbackView - SSO Authentication Callback Handler
 *
 * Handles the redirect from external SSO providers (OAuth2, SAML).
 * Extracts the token from query params, stores it, and redirects.
 * Issue #576 - User Management System Phase 4 (SSO).
 */

import { onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

onMounted(async () => {
  const token = route.query.token as string
  const error = route.query.error as string

  if (error) {
    router.push({ name: 'login', query: { error: 'sso_failed' } })
    return
  }

  if (token) {
    // Store token and fetch user info
    localStorage.setItem('slm_access_token', token)
    await authStore.checkAuth()
    router.push('/')
  } else {
    router.push({ name: 'login', query: { error: 'no_token' } })
  }
})
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
    <div class="text-center">
      <svg class="animate-spin h-10 w-10 text-primary-500 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="text-white text-lg">Completing SSO login...</p>
    </div>
  </div>
</template>
