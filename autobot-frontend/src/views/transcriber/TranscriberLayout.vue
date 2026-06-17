<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<script setup lang="ts">
// Layout shell — full sidebar implemented in Plan 4.
// Hosts the transcriber settings surface, including the cloud ASR provider
// selector (#10147c).
import { ref } from 'vue'
import AsrProviderSelector from '@/components/transcriber/AsrProviderSelector.vue'

const settingsOpen = ref(false)
</script>
<template>
  <div class="transcriber-layout">
    <header class="transcriber-layout-bar">
      <button
        type="button"
        class="btn btn-sm"
        :aria-expanded="settingsOpen"
        @click="settingsOpen = !settingsOpen"
      >
        {{ settingsOpen ? 'Hide settings' : 'Settings' }}
      </button>
    </header>

    <section v-if="settingsOpen" class="transcriber-layout-settings" aria-label="Transcriber settings">
      <h2 class="transcriber-layout-settings-heading">Transcriber settings</h2>
      <AsrProviderSelector />
    </section>

    <RouterView />
  </div>
</template>

<style scoped>
.transcriber-layout-bar {
  display: flex;
  justify-content: flex-end;
  padding: 0.5rem 1rem;
}

.transcriber-layout-settings {
  padding: 0 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.transcriber-layout-settings-heading {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}
</style>
