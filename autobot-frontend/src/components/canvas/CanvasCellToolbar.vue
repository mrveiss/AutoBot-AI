<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    class="absolute right-2 top-2 hidden group-hover:flex gap-1 bg-bg-elevated border border-border-default rounded shadow-sm z-10 p-1"
    role="toolbar"
    :aria-label="`Cell actions for cell ${cellId}`"
  >
    <button aria-label="Move cell up (⌘↑)" class="p-1 rounded hover:bg-bg-hover text-xs" @click.stop="$emit('move', 'up')">↑</button>
    <button aria-label="Move cell down (⌘↓)" class="p-1 rounded hover:bg-bg-hover text-xs" @click.stop="$emit('move', 'down')">↓</button>
    <button aria-label="Duplicate cell" class="p-1 rounded hover:bg-bg-hover text-xs" @click.stop="$emit('duplicate')">⧉</button>
    <button aria-label="Copy cell content" class="p-1 rounded hover:bg-bg-hover text-xs" @click.stop="$emit('copy')">⎘</button>
    <button aria-label="Delete cell" class="p-1 rounded hover:bg-bg-hover text-xs text-error" @click.stop="$emit('delete')">✕</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ cellId: string }>()
defineEmits<{
  move: [direction: 'up' | 'down']
  duplicate: []
  copy: []
  delete: []
}>()
</script>
