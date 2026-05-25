/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceBundle.ts — composable for per-user voice toolset bundle (GH#7422).
 *
 * User-facing: GET /api/voice/realtime/bundle/me → resolved bundle + tool list.
 * Admin-facing: PUT /api/admin/voice/bundle/{userId} → assign bundle to user.
 */

import { ref } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useVoiceBundle')

export const VOICE_BUNDLE_NAMES = ['voice_safe', 'voice_extended', 'voice_admin'] as const
export type VoiceBundleName = (typeof VOICE_BUNDLE_NAMES)[number]

export const VOICE_BUNDLE_LABELS: Record<VoiceBundleName, string> = {
  voice_safe: 'Voice Safe',
  voice_extended: 'Voice Extended',
  voice_admin: 'Voice Admin',
}

export interface UserBundleInfo {
  bundle_name: VoiceBundleName
  tool_count: number
  resolution: 'user_override' | 'role_default' | 'global_env'
}

export interface UserBundleAssignment {
  user_id: string
  bundle_name: VoiceBundleName | null
}

export function useVoiceBundle() {
  const bundleInfo = ref<UserBundleInfo | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchMyBundle(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await fetchWithAuth(`${getBackendUrl()}/api/voice/realtime/bundle/me`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
      }
      bundleInfo.value = (await res.json()) as UserBundleInfo
    } catch (err) {
      logger.error('Failed to fetch voice bundle info:', err)
      error.value = err instanceof Error ? err.message : 'Failed to load voice bundle'
      bundleInfo.value = null
    } finally {
      loading.value = false
    }
  }

  return { bundleInfo, loading, error, fetchMyBundle }
}

export function useAdminVoiceBundle() {
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  async function assignBundle(
    userId: string,
    bundleName: VoiceBundleName | null,
  ): Promise<boolean> {
    saving.value = true
    saveError.value = null
    try {
      const res = await fetchWithAuth(`${getBackendUrl()}/api/admin/voice/bundle/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bundle_name: bundleName }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
      }
      return true
    } catch (err) {
      logger.error('Failed to assign voice bundle:', err)
      saveError.value = err instanceof Error ? err.message : 'Failed to assign bundle'
      return false
    } finally {
      saving.value = false
    }
  }

  async function getUserBundle(userId: string): Promise<UserBundleAssignment | null> {
    try {
      const res = await fetchWithAuth(`${getBackendUrl()}/api/admin/voice/bundle/${userId}`)
      if (!res.ok) return null
      return (await res.json()) as UserBundleAssignment
    } catch {
      return null
    }
  }

  return { saving, saveError, assignBundle, getUserBundle }
}
