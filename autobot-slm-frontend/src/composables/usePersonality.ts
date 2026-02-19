// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Personality Profile Composable
 *
 * Manages AutoBot personality profiles via the backend REST API.
 * Provides reactive state for profile list, active profile, and enabled flag.
 *
 * Related Issue: #964 - Multi-profile personality system
 */

import axios from 'axios'
import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePersonality')

const API_BASE = '/autobot-api/personality'

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
}

export interface ProfileUpdate {
  name?: string
  tagline?: string
  tone?: string
  character_traits?: string[]
  operating_style?: string[]
  off_limits?: string[]
  custom_notes?: string
}

export const TONE_OPTIONS = [
  { value: 'direct', label: 'Direct' },
  { value: 'professional', label: 'Professional' },
  { value: 'casual', label: 'Casual' },
  { value: 'technical', label: 'Technical' },
] as const

export function usePersonality() {
  const authStore = useAuthStore()

  const profiles = ref<ProfileSummary[]>([])
  const activeProfile = ref<PersonalityProfile | null>(null)
  const enabled = ref(true)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeId = computed(() => profiles.value.find((p) => p.active)?.id ?? null)

  function _client() {
    const token = authStore.token || localStorage.getItem('autobot_access_token')
    return axios.create({
      baseURL: API_BASE,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      timeout: 15000,
    })
  }

  async function _call<T>(fn: () => Promise<T>): Promise<T | null> {
    error.value = null
    loading.value = true
    try {
      return await fn()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? 'Request failed'
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
        _client().get<ProfileSummary[]>('/profiles'),
        _client().get<{ enabled: boolean; active_id: string | null }>('/status'),
      ])
      return { summaries: summaries.data, status: status.data }
    })
    if (result) {
      profiles.value = result.summaries
      enabled.value = result.status.enabled
    }
  }

  async function fetchProfile(id: string): Promise<PersonalityProfile | null> {
    const result = await _call(() => _client().get<PersonalityProfile>(`/profiles/${id}`))
    return result?.data ?? null
  }

  async function fetchActive(): Promise<void> {
    const result = await _call(() =>
      _client().get<PersonalityProfile | null>('/active')
    )
    activeProfile.value = result?.data ?? null
  }

  async function createProfile(data: ProfileCreate): Promise<PersonalityProfile | null> {
    const result = await _call(() => _client().post<PersonalityProfile>('/profiles', data))
    if (result?.data) {
      await fetchProfiles()
      return result.data
    }
    return null
  }

  async function updateProfile(id: string, data: ProfileUpdate): Promise<PersonalityProfile | null> {
    const result = await _call(() => _client().put<PersonalityProfile>(`/profiles/${id}`, data))
    if (result?.data) {
      if (activeProfile.value?.id === id) {
        activeProfile.value = result.data
      }
      return result.data
    }
    return null
  }

  async function deleteProfile(id: string): Promise<boolean> {
    const result = await _call(() => _client().delete(`/profiles/${id}`))
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
    const result = await _call(() => _client().post(`/profiles/${id}/activate`))
    if (result !== null) {
      profiles.value = profiles.value.map((p) => ({ ...p, active: p.id === id }))
      await fetchActive()
      return true
    }
    return false
  }

  async function resetProfile(id: string): Promise<PersonalityProfile | null> {
    const result = await _call(() => _client().post<PersonalityProfile>(`/profiles/${id}/reset`))
    if (result?.data) {
      if (activeProfile.value?.id === id) {
        activeProfile.value = result.data
      }
      return result.data
    }
    return null
  }

  async function toggleEnabled(value: boolean): Promise<boolean> {
    const result = await _call(() =>
      _client().post('/toggle', { enabled: value })
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
