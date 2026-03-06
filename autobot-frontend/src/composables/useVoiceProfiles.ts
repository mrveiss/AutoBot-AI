/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceProfiles.ts - Voice profile management composable (#1054)
 * Manages TTS voice selection (built-in + custom voice profiles).
 */

import { ref, computed } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { usePreferences } from '@/composables/usePreferences'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useVoiceProfiles')

export interface VoiceProfile {
  id: string
  name: string
  builtin: boolean
  created?: string
}

const STORAGE_KEY = 'autobot-voice-profile-id'

// Module-level singletons for shared state
const voices = ref<VoiceProfile[]>([])
const selectedVoiceId = ref<string>(
  localStorage.getItem(STORAGE_KEY) || ''
)
const loading = ref(false)
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

export function useVoiceProfiles() {
  async function fetchVoices(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await fetchWithAuth('/api/voice/voices')
      if (!res.ok) {
        error.value = `Failed to fetch voices: ${res.status}`
        return
      }
      const data = await res.json()
      voices.value = Array.isArray(data) ? data : (data.voices || [])
    } catch (e) {
      logger.error('fetchVoices error:', e)
      error.value = String(e)
    } finally {
      loading.value = false
    }
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
    loading.value = true
    error.value = null
    try {
      const formData = new FormData()
      formData.append('name', name)
      formData.append('audio', audioBlob, filename)
      const res = await fetchWithAuth('/api/voice/voices/create', {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const body = await res.text()
        error.value = `Create voice failed: ${body}`
        return false
      }
      await fetchVoices()
      return true
    } catch (e) {
      logger.error('createVoice error:', e)
      error.value = String(e)
      return false
    } finally {
      loading.value = false
    }
  }

  async function deleteVoice(voiceId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const res = await fetchWithAuth(`/api/voice/voices/${voiceId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        error.value = `Delete voice failed: ${res.status}`
        return false
      }
      if (selectedVoiceId.value === voiceId) {
        selectVoice('')
      }
      await fetchVoices()
      return true
    } catch (e) {
      logger.error('deleteVoice error:', e)
      error.value = String(e)
      return false
    } finally {
      loading.value = false
    }
  }

  function setPersonalityVoice(voiceId: string): void {
    personalityVoiceId.value = voiceId
    logger.debug('Personality voice set:', voiceId || '(none)')
  }

  async function fetchPersonalityVoice(): Promise<void> {
    try {
      const res = await fetchWithAuth('/api/personality/active')
      if (res.ok) {
        const profile = await res.json()
        personalityVoiceId.value = profile?.voice_id ?? ''
        personalityVoiceIds.value = profile?.voice_ids ?? {}
      } else {
        personalityVoiceId.value = ''
        personalityVoiceIds.value = {}
      }
    } catch {
      personalityVoiceId.value = ''
      personalityVoiceIds.value = {}
    }
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
