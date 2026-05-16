<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <!-- Empty state -->
  <div
    v-if="state === 'empty'"
    class="flex flex-col items-center justify-center h-full gap-4 text-center p-8"
    data-testid="edge-empty"
  >
    <svg class="w-16 h-16 text-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    </svg>
    <h3 class="text-lg font-medium text-text-secondary">Your canvas is empty</h3>
    <button
      class="px-4 py-2 bg-autobot-primary text-white rounded-lg hover:opacity-90 flex items-center gap-2"
      aria-label="Add your first cell"
      @click="$emit('add-cell')"
    >
      <span class="text-lg" aria-hidden="true">+</span> Add your first cell
    </button>
  </div>

  <!-- Agent working (pre-stream, non-blocking) -->
  <div
    v-else-if="state === 'agent-working'"
    class="flex items-center gap-3 px-4 py-2 bg-bg-secondary border-b border-border-default text-sm text-text-secondary"
    role="status"
    aria-live="polite"
    data-testid="edge-agent-working"
  >
    <span class="animate-spin text-base" aria-hidden="true">⟳</span>
    Agent is working…
  </div>

  <!-- Stream error -->
  <div
    v-else-if="state === 'stream-error'"
    class="flex items-center gap-3 px-4 py-3 bg-autobot-error/10 border border-autobot-error/30 rounded m-4 text-sm"
    role="alert"
    data-testid="edge-stream-error"
  >
    <span class="text-autobot-error" aria-hidden="true">⚠</span>
    <span class="flex-1 text-text-primary">Stream failed. What would you like to do?</span>
    <button aria-label="Keep partial cell content" class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover" @click="$emit('keep')">Keep</button>
    <button aria-label="Retry stream" class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover" @click="$emit('retry')">Retry</button>
    <button aria-label="Discard errored cell" class="px-3 py-1 rounded border border-border-error text-error text-xs hover:bg-error-bg" @click="$emit('discard')">Discard</button>
  </div>

  <!-- Canvas load error -->
  <div
    v-else-if="state === 'load-error'"
    class="flex flex-col items-center justify-center h-full gap-4 text-center p-8"
    role="alert"
    data-testid="edge-load-error"
  >
    <span class="text-4xl" aria-hidden="true">⚠</span>
    <h3 class="text-lg font-medium">Failed to load canvas</h3>
    <button
      class="px-4 py-2 bg-autobot-primary text-white rounded hover:opacity-90"
      aria-label="Retry loading canvas"
      @click="$emit('retry')"
    >
      Retry
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  state: 'empty' | 'agent-working' | 'stream-error' | 'load-error' | null
}>()
defineEmits<{
  'add-cell': []
  keep: []
  retry: []
  discard: []
}>()
</script>
