// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useSlashCommands.ts - Composable for slash command detection and preset
 * autocomplete in chat input (GH#4449).
 */
import { ref, computed, type Ref } from 'vue'
import { useChatPresetsStore } from '@/stores/useChatPresetsStore'
import type { SlashCommandPreset } from '@/types/api'

/** Detects "/query" at end-of-text or after whitespace. */
const SLASH_PATTERN = /(?:^|\s)\/(\S*)$/

export function useSlashCommands(inputText: Ref<string>) {
  const presetsStore = useChatPresetsStore()

  const selectedIndex = ref(0)
  const isOpen = ref(false)

  const slashQuery = computed<string | null>(() => {
    const match = SLASH_PATTERN.exec(inputText.value)
    return match ? match[1] : null
  })

  const suggestions = computed<SlashCommandPreset[]>(() => {
    const query = slashQuery.value
    if (query === null) return []
    return presetsStore.filterByQuery(query)
  })

  const showDropdown = computed<boolean>(
    () => isOpen.value && suggestions.value.length > 0
  )

  function open(): void {
    selectedIndex.value = 0
    isOpen.value = true
  }

  function close(): void {
    isOpen.value = false
    selectedIndex.value = 0
  }

  function moveUp(): void {
    if (!showDropdown.value) return
    selectedIndex.value = (selectedIndex.value - 1 + suggestions.value.length) % suggestions.value.length
  }

  function moveDown(): void {
    if (!showDropdown.value) return
    selectedIndex.value = (selectedIndex.value + 1) % suggestions.value.length
  }

  /** Replace the slash query in the input with the selected preset's content. */
  function applyPreset(preset: SlashCommandPreset): string {
    return inputText.value.replace(SLASH_PATTERN, (full, _query, offset) => {
      const prefix = inputText.value.slice(0, offset)
      const space = prefix.trimEnd().length > 0 ? ' ' : ''
      return `${prefix}${space}${preset.content}`
    })
  }

  function confirmSelection(): SlashCommandPreset | null {
    if (!showDropdown.value) return null
    return suggestions.value[selectedIndex.value] ?? null
  }

  function onInput(): void {
    if (slashQuery.value !== null) {
      open()
    } else {
      close()
    }
  }

  function setSelectedIndex(idx: number): void {
    selectedIndex.value = idx
  }

  return {
    slashQuery,
    suggestions,
    showDropdown,
    selectedIndex,
    onInput,
    open,
    close,
    moveUp,
    moveDown,
    applyPreset,
    confirmSelection,
    setSelectedIndex,
    fetchPresets: presetsStore.fetchPresets,
    presetsLoading: computed(() => presetsStore.isLoading),
  }
}
