// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useSlmJsonSetting - shared GET-on-mount + PUT-then-POST-on-404 save for a
 * single SLM JSON settings-API key (#11359).
 *
 * `DisposalPolicySettings.vue` and `FindingsPolicySettings.vue` both fetch a
 * setting key, JSON.parse its `value` string, and save it back via
 * PUT (falling back to POST when the key doesn't exist yet). This composable
 * is the one shared implementation of that fetch/save mechanics; each panel
 * keeps its own field defaults, coercion, and error-message ownership (i18n
 * strings differ per panel).
 */

import { ref, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

export interface SlmJsonSetting<T> {
  saving: Ref<boolean>
  saved: Ref<boolean>
  /** GET the setting; returns the parsed JSON value, or null on a non-ok response. */
  load: () => Promise<T | null>
  /** PUT the setting (falling back to POST on 404); returns whether it succeeded. */
  save: (payload: T, description: string) => Promise<boolean>
}

export function useSlmJsonSetting<T>(key: string): SlmJsonSetting<T> {
  const authStore = useAuthStore()
  const saving = ref(false)
  const saved = ref(false)

  async function load(): Promise<T | null> {
    const res = await fetch(`${authStore.getApiUrl()}/api/settings/${key}`, {
      headers: authStore.getAuthHeaders(),
    })
    if (!res.ok) {
      return null
    }
    const setting = await res.json()
    return setting.value ? (JSON.parse(setting.value) as T) : ({} as T)
  }

  async function save(payload: T, description: string): Promise<boolean> {
    saving.value = true
    saved.value = false
    try {
      const url = `${authStore.getApiUrl()}/api/settings/${key}`
      const headers = { ...authStore.getAuthHeaders(), 'Content-Type': 'application/json' }
      const body = JSON.stringify({ value: JSON.stringify(payload), description })
      let res = await fetch(url, { method: 'PUT', headers, body })
      if (res.status === 404) {
        res = await fetch(url, { method: 'POST', headers, body })
      }
      saved.value = res.ok
      return res.ok
    } finally {
      saving.value = false
    }
  }

  return { saving, saved, load, save }
}
