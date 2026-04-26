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
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

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

// Module-level controllers — singleton state shared across all instances.
// Each controller is replaced (aborting the previous) before a new call.
// No onUnmounted is used because the singleton outlives individual components.
let _fetchVoicesController: AbortController | null = null
let _createVoiceController: AbortController | null = null
let _deleteVoiceController: AbortController | null = null
let _fetchPersonalityController: AbortController | null = null

export function useVoiceProfiles() {
  async function fetchVoices(): Promise<void> {
    error.value = null
    _fetchVoicesController?.abort()
    _fetchVoicesController = new AbortController()
    const signal = _fetchVoicesController.signal
    await wrap(async () => {
      const res = await fetchWithAuth(`${getApiBase()}/voice/voices`, { signal })
      if (!res.ok) {
        error.value = `Failed to fetch voices: ${res.status}`
        return
      }
      const data = await res.json()
      voices.value = Array.isArray(data) ? data : (data.voices || [])
    }).catch((e) => {
      if (e instanceof DOMException && e.name === 'AbortError') return
      logger.error('fetchVoices error:', e)
      error.value = String(e)
    })
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
    _createVoiceController?.abort()
    _createVoiceController = new AbortController()
    const signal = _createVoiceController.signal
    return wrap(async () => {
      const formData = new FormData()
      formData.append('name', name)
      formData.append('audio', audioBlob, filename)
      const res = await fetchWithAuth(`${getApiBase()}/voice/voices/create`, {
        method: 'POST',
        body: formData,
        signal,
      })
      if (!res.ok) {
        const body = await res.text()
        error.value = `Create voice failed: ${body}`
        return false
      }
      await fetchVoices()
      return true
    }).catch((e) => {
      if (e instanceof DOMException && e.name === 'AbortError') return false
      logger.error('createVoice error:', e)
      error.value = String(e)
      return false
    })
  }

  async function deleteVoice(voiceId: string): Promise<boolean> {
    error.value = null
    _deleteVoiceController?.abort()
    _deleteVoiceController = new AbortController()
    const signal = _deleteVoiceController.signal
    return wrap(async () => {
      const res = await fetchWithAuth(`${getApiBase()}/voice/voices/${voiceId}`, {
        method: 'DELETE',
        signal,
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
    }).catch((e) => {
      if (e instanceof DOMException && e.name === 'AbortError') return false
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
    _fetchPersonalityController?.abort()
    _fetchPersonalityController = new AbortController()
    const signal = _fetchPersonalityController.signal
    try {
      const res = await fetchWithAuth(`${getApiBase()}/personality/active`, { signal })
      if (res.ok) {
        const profile = await res.json()
        personalityVoiceId.value = profile?.voice_id ?? ''
        personalityVoiceIds.value = profile?.voice_ids ?? {}
      } else {
        personalityVoiceId.value = ''
        personalityVoiceIds.value = {}
      }
    } catch (e) {
      if (e instanceof DOMException && (e as DOMException).name === 'AbortError') return
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
