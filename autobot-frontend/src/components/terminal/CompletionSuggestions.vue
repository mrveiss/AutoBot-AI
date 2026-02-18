<template>
  <div
    v-if="visible && items.length > 0"
    class="completion-suggestions"
    role="listbox"
    :aria-label="'Completion suggestions'"
  >
    <div
      v-for="(item, index) in items"
      :key="item.value"
      class="completion-item"
      :class="{
        'selected': index === selectedIndex,
        [`type-${item.type}`]: true
      }"
      role="option"
      :aria-selected="index === selectedIndex"
      @mousedown.prevent="$emit('select', index)"
    >
      <span class="item-icon">{{ typeIcon(item.type) }}</span>
      <span class="item-value">{{ item.value }}</span>
      <span v-if="item.description" class="item-desc">{{ item.description }}</span>
    </div>
    <div class="completion-hint">
      Tab to cycle | Enter to accept | Esc to dismiss
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CompletionItem } from '@/composables/useTabCompletion'

interface Props {
  items: CompletionItem[]
  selectedIndex: number
  visible: boolean
}

defineProps<Props>()
defineEmits<{
  (e: 'select', index: number): void
}>()

const typeIcon = (type: string): string => {
  switch (type) {
    case 'command': return '$'
    case 'path': return '/'
    case 'history': return '#'
    case 'argument': return '-'
    default: return '>'
  }
}
</script>

<style scoped>
.completion-suggestions {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 200px;
  overflow-y: auto;
  background-color: #1e1e1e;
  border: 1px solid #444;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  z-index: 100;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
}

.completion-item {
  display: flex;
  align-items: center;
  padding: 4px 12px;
  cursor: pointer;
  gap: 8px;
  transition: background-color 0.1s;
}

.completion-item:hover,
.completion-item.selected {
  background-color: #264f78;
}

.item-icon {
  color: #888;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
  font-weight: bold;
}

.type-command .item-icon { color: #87ceeb; }
.type-path .item-icon { color: #98c379; }
.type-history .item-icon { color: #e5c07b; }
.type-argument .item-icon { color: #c678dd; }

.item-value {
  color: #ffffff;
  flex-shrink: 0;
}

.item-desc {
  color: #666;
  margin-left: auto;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.completion-hint {
  padding: 2px 12px;
  font-size: 10px;
  color: #555;
  border-top: 1px solid #333;
  text-align: center;
}

/* Scrollbar */
.completion-suggestions::-webkit-scrollbar {
  width: 6px;
}

.completion-suggestions::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.completion-suggestions::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 3px;
}
</style>
