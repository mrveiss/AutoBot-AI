<template>
  <Teleport to="body">
    <div
      v-if="show"
      ref="dropdownEl"
      class="slash-command-dropdown"
      :style="positionStyle"
      role="listbox"
      aria-label="Slash command suggestions"
      @mousedown.prevent
    >
      <div
        v-for="(preset, idx) in suggestions"
        :key="preset.id"
        class="slash-command-item"
        :class="{ 'selected': idx === selectedIndex }"
        role="option"
        :aria-selected="idx === selectedIndex"
        @click="$emit('select', preset)"
        @mouseenter="$emit('update:selectedIndex', idx)"
      >
        <span class="slash-command-name">/{{ preset.name }}</span>
        <span class="slash-command-desc">{{ preset.description }}</span>
      </div>
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
    zIndex: 9999,
  }
})

watch(
  () => props.selectedIndex,
  async (idx) => {
    await nextTick()
    const items = dropdownEl.value?.querySelectorAll<HTMLElement>('.slash-command-item')
    items?.[idx]?.scrollIntoView({ block: 'nearest' })
  }
)
</script>

<style scoped>
.slash-command-dropdown {
  background: var(--autobot-surface, #1e1e2e);
  border: 1px solid var(--autobot-border, #313244);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  max-height: 240px;
  overflow-y: auto;
}

.slash-command-item {
  display: flex;
  flex-direction: column;
  padding: 8px 12px;
  cursor: pointer;
  gap: 2px;
}

.slash-command-item:hover,
.slash-command-item.selected {
  background: var(--autobot-surface-hover, #313244);
}

.slash-command-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--autobot-primary, #cba6f7);
  font-family: monospace;
}

.slash-command-desc {
  font-size: 0.75rem;
  color: var(--autobot-text-secondary, #a6adc8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
