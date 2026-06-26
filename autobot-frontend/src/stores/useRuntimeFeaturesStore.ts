// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #10502: Reactive runtime feature flags sourced from GET /api/frontend-config.
// These flags reflect the *deployment* (e.g. PostgreSQL company mode) rather
// than build-time VITE_* env toggles, so they must be fetched at runtime and
// shared across the nav rail and gated views. Fetched once per session.

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useRuntimeFeaturesStore')

/** Subset of the backend frontend-config `features` block the UI gates on. */
export interface RuntimeFeatures {
  company_os_enabled: boolean
}

interface FrontendConfigResponse {
  features?: Partial<RuntimeFeatures>
}

export const useRuntimeFeaturesStore = defineStore('runtimeFeatures', () => {
  // Default fail-closed for deployment-gated modules: hidden until the backend
  // confirms availability, so single_user deployments never surface a 503 view.
  const features = ref<RuntimeFeatures>({ company_os_enabled: false })
  const isLoaded = ref(false)
  const isLoading = ref(false)

  const companyOsEnabled = computed(() => features.value.company_os_enabled)

  /** Fetch runtime features once (parsed JSON, no envelope). Idempotent. */
  async function load(): Promise<void> {
    if (isLoaded.value || isLoading.value) return
    isLoading.value = true
    try {
      const resp = await apiClient.get<FrontendConfigResponse>(`${getApiBase()}/frontend-config`)
      features.value = {
        company_os_enabled: resp?.features?.company_os_enabled === true,
      }
      isLoaded.value = true
    } catch (err) {
      // Leave defaults (fail-closed) on failure; surface for diagnostics only.
      logger.warn('Failed to load runtime features, using fail-closed defaults:', err)
    } finally {
      isLoading.value = false
    }
  }

  return {
    features,
    isLoaded,
    isLoading,
    companyOsEnabled,
    load,
  }
})
