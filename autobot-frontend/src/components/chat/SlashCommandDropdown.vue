<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SlashCommandDropdown -- the preset suggestions that open above the composer while a `/query` is typed
  (GH#4449, #18243): a listbox on the kit tokens, with the keys it answers to named in its footer. The
  keyboard handling stays in the composer's textarea (`useComposerInput`); focus never leaves it, so the
  rows are `aria-selected` options and `mousedown` is prevented.
-->
<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="flex max-h-60 flex-col overflow-y-auto rounded-[var(--aui-radius-lg)] border border-[var(--aui-color-border)] bg-[var(--aui-color-surface)] p-1 shadow-[var(--aui-shadow-lg)]"
      :style="positionStyle"
      @mousedown.prevent
    >
      <span class="px-3 py-1 text-xs text-[var(--aui-color-text-muted)]">{{ $t('chat.input.slashPresets') }}</span>
      <div ref="dropdownEl" role="listbox" :aria-label="$t('chat.input.slashSuggestions')">
      <div
        v-for="(preset, idx) in suggestions"
        :key="preset.id"
        class="flex cursor-pointer items-baseline gap-3 rounded-[var(--aui-radius-md)] px-3 py-2 hover:bg-[var(--aui-color-surface-raised)]"
        :class="{ 'bg-[var(--aui-color-surface-raised)]': idx === selectedIndex }"
        data-slash-item
        role="option"
        :aria-selected="idx === selectedIndex"
        @click="$emit('select', preset)"
        @mouseenter="$emit('update:selectedIndex', idx)"
      >
        <span class="font-mono text-sm font-semibold text-[var(--aui-color-text)]">/{{ preset.name }}</span>
        <span class="min-w-0 flex-1 truncate text-xs text-[var(--aui-color-text-muted)]">{{ preset.description }}</span>
        <kbd v-if="idx === selectedIndex" class="rounded-[var(--aui-radius-sm)] border border-[var(--aui-color-border-strong)] px-1 font-mono text-xs text-[var(--aui-color-text-muted)]" aria-hidden="true">↵</kbd>
      </div>
      </div>
      <span class="px-3 py-1 text-xs text-[var(--aui-color-text-muted)]">{{ $t('chat.input.slashHint') }}</span>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { SlashCommandPreset } from '@/types/api'

const props = defineProps<{
  show: boolean
  suggestions: SlashCommandPreset[]
  selectedIndex: number
  anchorEl: HTMLElement | null
}>()

defineEmits<{
  select: [preset: SlashCommandPreset]
  'update:selectedIndex': [idx: number]
}>()

const dropdownEl = ref<HTMLElement>()

const positionStyle = computed(() => {
  if (!props.anchorEl) return {}
  const rect = props.anchorEl.getBoundingClientRect()
  return {
    position: 'fixed' as const,
    bottom: `${window.innerHeight - rect.top + 8}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    zIndex: 'var(--aui-z-popover)',
  }
})

watch(
  () => props.selectedIndex,
  async (idx) => {
    await nextTick()
    const items = dropdownEl.value?.querySelectorAll<HTMLElement>('[data-slash-item]')
    items?.[idx]?.scrollIntoView({ block: 'nearest' })
  }
)
</script>
