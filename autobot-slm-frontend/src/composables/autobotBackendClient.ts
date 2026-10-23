// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The SLM's one HTTP client for the MAIN AutoBot backend (#19217).
 *
 * `useAutobotApi` and the per-feature admin composables (e.g. `useWebResearchAdminApi`)
 * all talk to the main backend with the SLM session token. They share this factory, so
 * the base URL, timeout and auth header are declared once instead of copied per composable.
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

export function createAutobotBackendClient(): AxiosInstance {
  const authStore = useAuthStore()
  const client = axios.create({
    baseURL: getBackendUrl(),
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
  })
  // The SLM session token; nothing writes `autobot_access_token`, so the old
  // fallback to it is gone (#17856 row 8)
  client.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })
  return client
}
