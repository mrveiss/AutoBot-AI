/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceProfiles.ts - Voice profile management composable (#1054)
 * Manages TTS voice selection (built-in + custom voice profiles).
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
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

  return {
    voices,
    selectedVoiceId,
    loading,
    error,
    fetchVoices,
    selectVoice,
    createVoice,
    deleteVoice,
  }
}
