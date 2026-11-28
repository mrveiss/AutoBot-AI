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
  background-color: var(--terminal-chrome-bg-alt);
  border: 1px solid var(--terminal-border);
  border-bottom: none;
  border-radius: var(--radius-default) 4px 0 0;
  z-index: var(--z-popover);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: var(--text-sm);
}

.completion-item {
  display: flex;
  align-items: center;
  padding: var(--spacing-1) var(--spacing-3);
  cursor: pointer;
  gap: var(--spacing-2);
  transition: background-color var(--duration-100);
}

.completion-item:hover,
.completion-item.selected {
  background-color: var(--terminal-selection-bg);
}

.item-icon {
  color: var(--terminal-text-muted);
  width: 16px;
  text-align: center;
  flex-shrink: 0;
  font-weight: bold;
}

.type-command .item-icon { color: var(--terminal-ansi-cyan); }
.type-path .item-icon { color: var(--terminal-syntax-path); }
.type-history .item-icon { color: var(--terminal-syntax-history); }
.type-argument .item-icon { color: var(--terminal-syntax-argument); }

.item-value {
  color: var(--terminal-text);
  flex-shrink: 0;
}

.item-desc {
  color: var(--terminal-border-strong);
  margin-left: auto;
  font-size: var(--text-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.completion-hint {
  padding: var(--spacing-0-5) var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--terminal-text-faint);
  border-top: 1px solid var(--terminal-border-subtle);
  text-align: center;
}

/* Scrollbar */
.completion-suggestions::-webkit-scrollbar {
  width: 6px;
}

.completion-suggestions::-webkit-scrollbar-track {
  background: var(--terminal-chrome-bg-alt);
}

.completion-suggestions::-webkit-scrollbar-thumb {
  background: var(--terminal-btn-hover-bg);
  border-radius: var(--radius-default);
}
</style>
