<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <suspense>
    <canvas-root canvas-id="default" @focus-chat="onFocusChat" />
    <template #fallback>
      <div class="flex items-center justify-center h-full text-text-secondary text-sm">
        Loading canvas…
      </div>
    </template>
  </suspense>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

const CanvasRoot = defineAsyncComponent(() =>
  import('@/components/canvas/CanvasView.vue')
)

function onFocusChat() {
  // Will wire to chat interface in sibling A integration
}
</script>
