<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    v-if="conflict"
    class="flex items-center gap-3 px-4 py-2 bg-autobot-warning/10 border-b border-autobot-warning/30 text-sm"
    role="alert"
    aria-live="assertive"
  >
    <span class="font-medium">⚡ Conflict</span>
    <span class="text-text-secondary flex-1">
      You edited a cell the agent was writing. The agent will continue in a new cell below.
    </span>
    <button
      aria-label="Resume agent writing in a new cell"
      class="px-3 py-1 rounded bg-autobot-primary text-white text-xs hover:opacity-90"
      @click="$emit('resume')"
    >
      Resume
    </button>
    <button
      aria-label="Dismiss conflict banner"
      class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover"
      @click="$emit('dismiss')"
    >
      Dismiss
    </button>
  </div>
</template>

<script setup lang="ts">
import type { ConflictState } from '@/types/canvas'
defineProps<{ conflict: ConflictState | null }>()
defineEmits<{ resume: []; dismiss: [] }>()
</script>
