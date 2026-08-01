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
 *
 * The transport itself lives in `utils/slmSettingsApi.ts` on top of the
 * canonical `slmApiClient` (#13140) — this composable no longer builds its own
 * URL or auth headers, so it inherits `getSlmApiBase()` origin resolution, the
 * sessionStorage/localStorage token fallback, the request timeout and the 401
 * session handler.
 */

import { ref, type Ref } from 'vue'
import { getSetting, upsertSetting } from '@/utils/slmSettingsApi'

export interface SlmJsonSetting<T> {
  saving: Ref<boolean>
  saved: Ref<boolean>
  /** GET the setting; returns the parsed JSON value, or null on a non-ok response. */
  load: () => Promise<T | null>
  /** PUT the setting (falling back to POST on 404); returns whether it succeeded. */
  save: (payload: T, description: string) => Promise<boolean>
}

export function useSlmJsonSetting<T>(key: string): SlmJsonSetting<T> {
  const saving = ref(false)
  const saved = ref(false)

  async function load(): Promise<T | null> {
    const setting = await getSetting(key)
    if (setting === null) {
      return null
    }
    return setting.value ? (JSON.parse(setting.value) as T) : ({} as T)
  }

  async function save(payload: T, description: string): Promise<boolean> {
    saving.value = true
    saved.value = false
    try {
      const ok = await upsertSetting(key, {
        value: JSON.stringify(payload),
        description,
      })
      saved.value = ok
      return ok
    } finally {
      saving.value = false
    }
  }

  return { saving, saved, load, save }
}
