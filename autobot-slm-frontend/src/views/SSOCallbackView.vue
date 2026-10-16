// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * SSOCallbackView - SSO Authentication Callback Handler
 *
 * Handles the redirect from external SSO providers (OAuth2, SAML).
 * Reads the one-time `code` from the query, immediately strips it from
 * history, and exchanges it by POST for the session token. The token never
 * travels in a URL (#18394). Issue #576 - User Management System Phase 4 (SSO).
 */

import { onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { slmApiClient } from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SSOCallbackView')
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

async function exchangeCode(code: string): Promise<string | null> {
  const response = await slmApiClient.rawRequest('/auth/sso/exchange', {
    method: 'POST',
    body: { code },
  })
  if (!response.ok) return null
  const data = await response.json()
  return data.access_token ?? null
}

onMounted(async () => {
  const code = route.query.code as string
  const error = route.query.error as string

  // Drop the one-time code (and any leftover token param) from history.
  window.history.replaceState(window.history.state, '', window.location.pathname)

  if (error) {
    router.push({ name: 'login', query: { error: 'sso_failed' } })
    return
  }

  if (!code) {
    router.push({ name: 'login', query: { error: 'no_token' } })
    return
  }

  try {
    const token = await exchangeCode(code)
    if (!token) {
      router.push({ name: 'login', query: { error: 'sso_failed' } })
      return
    }
    authStore.adoptToken(token)
    await authStore.checkAuth()
    router.push('/')
  } catch (e) {
    logger.error('SSO code exchange failed', e)
    router.push({ name: 'login', query: { error: 'sso_failed' } })
  }
})
</script>

<template>
  <div class="min-h-screen bg-slate-900 flex items-center justify-center">
    <div class="text-center">
      <svg class="animate-spin h-10 w-10 text-primary-500 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="text-white text-lg">{{ $t('sSOCallbackView.completingSSOLogin') }}</p>
    </div>
  </div>
</template>
