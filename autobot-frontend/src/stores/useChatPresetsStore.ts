// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type {
  SlashCommandPreset,
  SlashCommandPresetCreate,
  SlashCommandPresetUpdate,
} from '@/types/api'

const logger = createLogger('useChatPresetsStore')

const PRESETS_ENDPOINT = '/api/chat/presets'

export const useChatPresetsStore = defineStore('chatPresets', () => {
  const presets = ref<SlashCommandPreset[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Sorted alphabetically by name for consistent dropdown ordering
  const sortedPresets = computed<SlashCommandPreset[]>(() =>
    [...presets.value].sort((a, b) => a.name.localeCompare(b.name))
  )

  function filterByQuery(query: string): SlashCommandPreset[] {
    const lower = query.toLowerCase()
    return sortedPresets.value.filter(
      (p) => p.name.toLowerCase().startsWith(lower) || p.description.toLowerCase().includes(lower)
    )
  }

  async function fetchPresets(): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    error.value = null
    try {
      const data = await api.get<SlashCommandPreset[]>(PRESETS_ENDPOINT)
      presets.value = data
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load presets'
      logger.error('[useChatPresetsStore] fetchPresets failed:', err)
    } finally {
      isLoading.value = false
    }
  }

  async function createPreset(payload: SlashCommandPresetCreate): Promise<SlashCommandPreset | null> {
    const api = useApiClient()
    error.value = null
    try {
      const created = await api.post<SlashCommandPreset>(PRESETS_ENDPOINT, payload)
      presets.value.push(created)
      return created
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create preset'
      logger.error('[useChatPresetsStore] createPreset failed:', err)
      return null
    }
  }

  async function updatePreset(id: string, payload: SlashCommandPresetUpdate): Promise<SlashCommandPreset | null> {
    const api = useApiClient()
    error.value = null
    try {
      const updated = await api.put<SlashCommandPreset>(`${PRESETS_ENDPOINT}/${id}`, payload)
      const idx = presets.value.findIndex((p) => p.id === id)
      if (idx !== -1) presets.value[idx] = updated
      return updated
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update preset'
      logger.error('[useChatPresetsStore] updatePreset failed:', err)
      return null
    }
  }

  async function deletePreset(id: string): Promise<boolean> {
    const api = useApiClient()
    error.value = null
    try {
      await api.delete(`${PRESETS_ENDPOINT}/${id}`)
      presets.value = presets.value.filter((p) => p.id !== id)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete preset'
      logger.error('[useChatPresetsStore] deletePreset failed:', err)
      return false
    }
  }

  return {
    presets,
    sortedPresets,
    isLoading,
    error,
    filterByQuery,
    fetchPresets,
    createPreset,
    updatePreset,
    deletePreset,
  }
})
