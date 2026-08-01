// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Personality Profile Composable
 *
 * Manages AutoBot personality profiles via the backend REST API.
 * Provides reactive state for profile list, active profile, and enabled flag.
 *
 * Related Issue: #964 - Multi-profile personality system
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()` and injects the SLM bearer token
 * (the `slm_access_token` the auth store reads), so endpoints are passed
 * relative to the SLM API base under the `/personality` prefix and callers
 * receive parsed JSON directly (no axios `.data`). Requests still route through
 * the SLM backend proxy (issue #1145) which validates the SLM JWT and forwards
 * to the main backend, so the SLM token is the correct credential.
 */

import { ref, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import slmApiClient from '@/utils/ApiClient'

const logger = createLogger('usePersonality')

// Issue #1145: Route through SLM backend proxy (validates SLM JWT + forwards to main backend).
// Using /autobot-api/personality caused JWT mismatch since SLM tokens are unknown to main backend.
// Endpoints below are relative to getSlmApiBase() (resolved by slmApiClient) under this prefix.
const API_PREFIX = '/personality'

export interface ProfileSummary {
  id: string
  name: string
  is_system: boolean
  active: boolean
}

export interface PersonalityProfile {
  id: string
  name: string
  tagline: string
  tone: 'direct' | 'professional' | 'casual' | 'technical'
  character_traits: string[]
  operating_style: string[]
  off_limits: string[]
  custom_notes: string
  voice_id: string
  voice_ids: Record<string, string>
  is_system: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface ProfileCreate {
  name: string
  tagline?: string
  tone?: string
  character_traits?: string[]
  operating_style?: string[]
  off_limits?: string[]
  custom_notes?: string
  voice_id?: string
  voice_ids?: Record<string, string>
}

export interface ProfileUpdate {
  name?: string
  tagline?: string
  tone?: string
  character_traits?: string[]
  operating_style?: string[]
  off_limits?: string[]
  custom_notes?: string
  voice_id?: string
  voice_ids?: Record<string, string>
}

export const TONE_OPTIONS = [
  { value: 'direct', label: 'Direct' },
  { value: 'professional', label: 'Professional' },
  { value: 'casual', label: 'Casual' },
  { value: 'technical', label: 'Technical' },
] as const

export function usePersonality() {
  const profiles = ref<ProfileSummary[]>([])
  const activeProfile = ref<PersonalityProfile | null>(null)
  const enabled = ref(true)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeId = computed(() => profiles.value.find((p) => p.active)?.id ?? null)

  async function _call<T>(fn: () => Promise<T>): Promise<T | null> {
    error.value = null
    loading.value = true
    try {
      return await fn()
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message ?? 'Request failed'
      error.value = msg
      logger.error('Personality API error:', msg)
      return null
    } finally {
      loading.value = false
    }
  }

  async function fetchProfiles(): Promise<void> {
    const result = await _call(async () => {
      const [summaries, status] = await Promise.all([
        slmApiClient.get<ProfileSummary[]>(`${API_PREFIX}/profiles`),
        slmApiClient.get<{ enabled: boolean; active_id: string | null }>(
          `${API_PREFIX}/status`
        ),
      ])
      return { summaries, status }
    })
    if (result) {
      profiles.value = result.summaries
      enabled.value = result.status.enabled
    }
  }

  async function fetchProfile(id: string): Promise<PersonalityProfile | null> {
    return _call(() =>
      slmApiClient.get<PersonalityProfile>(`${API_PREFIX}/profiles/${id}`)
    )
  }

  async function fetchActive(): Promise<void> {
    const result = await _call(() =>
      slmApiClient.get<PersonalityProfile | null>(`${API_PREFIX}/active`)
    )
    activeProfile.value = result ?? null
  }

  async function createProfile(data: ProfileCreate): Promise<PersonalityProfile | null> {
    const result = await _call(() =>
      slmApiClient.post<PersonalityProfile>(`${API_PREFIX}/profiles`, data)
    )
    if (result) {
      await fetchProfiles()
      return result
    }
    return null
  }

  async function updateProfile(id: string, data: ProfileUpdate): Promise<PersonalityProfile | null> {
    const result = await _call(() =>
      slmApiClient.put<PersonalityProfile>(`${API_PREFIX}/profiles/${id}`, data)
    )
    if (result) {
      if (activeProfile.value?.id === id) {
        activeProfile.value = result
      }
      return result
    }
    return null
  }

  async function deleteProfile(id: string): Promise<boolean> {
    const result = await _call(() =>
      slmApiClient.delete(`${API_PREFIX}/profiles/${id}`)
    )
    if (result !== null) {
      profiles.value = profiles.value.filter((p) => p.id !== id)
      if (activeProfile.value?.id === id) {
        activeProfile.value = null
      }
      return true
    }
    return false
  }

  async function activateProfile(id: string): Promise<boolean> {
    const result = await _call(() =>
      slmApiClient.post(`${API_PREFIX}/profiles/${id}/activate`)
    )
    if (result !== null) {
      profiles.value = profiles.value.map((p) => ({ ...p, active: p.id === id }))
      await fetchActive()
      return true
    }
    return false
  }

  async function resetProfile(id: string): Promise<PersonalityProfile | null> {
    const result = await _call(() =>
      slmApiClient.post<PersonalityProfile>(`${API_PREFIX}/profiles/${id}/reset`)
    )
    if (result) {
      if (activeProfile.value?.id === id) {
        activeProfile.value = result
      }
      return result
    }
    return null
  }

  async function toggleEnabled(value: boolean): Promise<boolean> {
    const result = await _call(() =>
      slmApiClient.post(`${API_PREFIX}/toggle`, { enabled: value })
    )
    if (result !== null) {
      enabled.value = value
      return true
    }
    return false
  }

  return {
    profiles,
    activeProfile,
    enabled,
    loading,
    error,
    activeId,
    fetchProfiles,
    fetchProfile,
    fetchActive,
    createProfile,
    updateProfile,
    deleteProfile,
    activateProfile,
    resetProfile,
    toggleEnabled,
    TONE_OPTIONS,
  }
}
