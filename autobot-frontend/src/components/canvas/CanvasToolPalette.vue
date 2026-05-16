<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    class="flex items-center gap-1 px-3 py-1.5 bg-bg-secondary border-b border-border-default"
    role="toolbar"
    aria-label="Canvas toolbar"
  >
    <button
      data-testid="canvas-undo-btn"
      aria-label="Undo (⌘Z)"
      :disabled="!canUndo"
      class="p-1.5 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed"
      @click="store.undo()"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a4 4 0 010 8H7m-4-8l4-4m-4 4l4 4"/></svg>
    </button>

    <button
      data-testid="canvas-redo-btn"
      aria-label="Redo (⌘⇧Z)"
      :disabled="!canRedo"
      class="p-1.5 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed"
      @click="store.redo()"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 10H11a4 4 0 000 8h6m4-8l-4-4m4 4l-4 4"/></svg>
    </button>

    <div class="w-px h-5 bg-border-default mx-1" role="separator" aria-hidden="true" />

    <button
      data-testid="canvas-add-cell-btn"
      aria-label="Add cell"
      class="p-1.5 rounded hover:bg-bg-hover flex items-center gap-1 text-sm"
      @click="store.addCell('user')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
      Add cell
    </button>

    <div class="flex-1" />

    <!-- Auto-save status indicator -->
    <span
      data-testid="canvas-save-status"
      :class="['text-xs', saveStatusClass]"
      aria-live="polite"
      aria-atomic="true"
    >
      {{ saveStatusText }}
    </span>

    <button
      v-if="saveStatus === 'error'"
      class="text-xs text-autobot-primary underline ml-1"
      aria-label="Retry save"
      @click="$emit('retry-save')"
    >
      Retry
    </button>

    <div class="w-px h-5 bg-border-default mx-1" role="separator" aria-hidden="true" />

    <button
      data-testid="canvas-export-btn"
      aria-label="Export canvas (⌘⇧E)"
      class="p-1.5 rounded hover:bg-bg-hover flex items-center gap-1 text-sm"
      @click="$emit('export')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      Export
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { AutoSaveStatus } from '@/types/canvas'

const props = defineProps<{ saveStatus: AutoSaveStatus; lastSavedAt?: string }>()
defineEmits<{ export: []; 'retry-save': [] }>()

const store = useCanvasStore()
const canUndo = computed(() => store.canUndo)
const canRedo = computed(() => store.canRedo)

const saveStatusText = computed(() => {
  switch (props.saveStatus) {
    case 'saving': return '💾 Saving…'
    case 'saved': return props.lastSavedAt ? `✓ Saved ${props.lastSavedAt}` : '✓ Saved'
    case 'error': return '⚠ Save failed'
    default: return ''
  }
})

const saveStatusClass = computed(() => ({
  'text-text-secondary': props.saveStatus === 'saving' || props.saveStatus === 'idle',
  'text-autobot-success': props.saveStatus === 'saved',
  'text-autobot-error': props.saveStatus === 'error',
}))
</script>
