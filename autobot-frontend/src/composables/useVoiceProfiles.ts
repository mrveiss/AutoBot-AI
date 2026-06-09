// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useVoiceProfiles.ts - Voice profile management composable (#1054)
 * Manages TTS voice selection (built-in + custom voice profiles).
 */

import { ref, computed } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
import { usePreferences } from '@/composables/usePreferences'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useVoiceProfiles')

export interface VoiceProfile {
  id: string
  name: string
  builtin: boolean
  created?: string
}

interface VoicesRaw {
  voices?: VoiceProfile[]
}

interface PersonalityRaw {
  voice_id?: string
  voice_ids?: Record<string, string>
}

const STORAGE_KEY = 'autobot-voice-profile-id'

// Module-level singletons for shared state
const voices = ref<VoiceProfile[]>([])
const selectedVoiceId = ref<string>(
  localStorage.getItem(STORAGE_KEY) || ''
)
// loading and wrap are module-level to preserve the singleton pattern
const { isLoading: loading, wrap } = useLoadingState()
const error = ref<string | null>(null)
// Personality-assigned voice — overrides user selection when set (#1135)
const personalityVoiceId = ref<string>('')
// Per-language voice map from personality profile (#1333)
const personalityVoiceIds = ref<Record<string, string>>({})
const effectiveVoiceId = computed<string>(() => {
  // Voice resolution order (#1333):
  // 1. voice_ids[current_language] (language-specific)
  // 2. voice_id (profile default, backward compatible)
  // 3. User-selected voice (selectedVoiceId)
  const { language } = usePreferences()
  const lang = language.value || 'en'
  const langVoice = personalityVoiceIds.value[lang]
  if (langVoice) return langVoice
  if (personalityVoiceId.value) return personalityVoiceId.value
  return selectedVoiceId.value
})

// GET voices — useFetchEndpoint provides AbortController + race protection
const voicesEndpoint = useFetchEndpoint<VoicesRaw, VoiceProfile[]>({
  path: '/api/voice/voices',
  label: 'fetchVoices',
  pickData: (raw) => {
    const list = Array.isArray(raw) ? (raw as unknown as VoiceProfile[]) : (raw.voices ?? null)
    return list
  },
  onSuccess: (data) => {
    voices.value = data
  },
  onError: (message) => {
    logger.error('fetchVoices error:', message)
    error.value = message
  },
})

// GET active personality — useFetchEndpoint provides AbortController + race protection
const personalityEndpoint = useFetchEndpoint<PersonalityRaw, PersonalityRaw>({
  path: '/api/personality/active',
  label: 'fetchPersonalityVoice',
  pickData: (raw) => raw ?? null,
  onSuccess: (data) => {
    personalityVoiceId.value = data.voice_id ?? ''
    personalityVoiceIds.value = data.voice_ids ?? {}
  },
  onError: () => {
    personalityVoiceId.value = ''
    personalityVoiceIds.value = {}
  },
  onNoData: () => {
    personalityVoiceId.value = ''
    personalityVoiceIds.value = {}
  },
})

export function useVoiceProfiles() {
  const api = useApiClient()

  async function fetchVoices(): Promise<void> {
    error.value = null
    await voicesEndpoint.load()
  }

  function selectVoice(voiceId: string): void {
    selectedVoiceId.value = voiceId
    localStorage.setItem(STORAGE_KEY, voiceId)
    logger.debug('Voice selected:', voiceId)
  }

  async function createVoice(
    name: string,
    audioBlob: Blob,
    filename: string,
  ): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      const formData = new FormData()
      formData.append('name', name)
      formData.append('audio', audioBlob, filename)
      await api.post(`${getApiBase()}/voice/voices/create`, formData)
      await fetchVoices()
      return true
    }).catch((e: unknown) => {
      logger.error('createVoice error:', e)
      error.value = String(e)
      return false
    })
  }

  async function deleteVoice(voiceId: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await api.delete(`${getApiBase()}/voice/voices/${voiceId}`)
      if (selectedVoiceId.value === voiceId) {
        selectVoice('')
      }
      await fetchVoices()
      return true
    }).catch((e: unknown) => {
      logger.error('deleteVoice error:', e)
      error.value = String(e)
      return false
    })
  }

  function setPersonalityVoice(voiceId: string): void {
    personalityVoiceId.value = voiceId
    logger.debug('Personality voice set:', voiceId || '(none)')
  }

  async function fetchPersonalityVoice(): Promise<void> {
    await personalityEndpoint.load()
  }

  return {
    voices,
    selectedVoiceId,
    personalityVoiceId,
    personalityVoiceIds,
    effectiveVoiceId,
    loading,
    error,
    fetchVoices,
    selectVoice,
    createVoice,
    deleteVoice,
    setPersonalityVoice,
    fetchPersonalityVoice,
  }
}
