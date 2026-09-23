<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<script setup lang="ts">
// Layout shell — full sidebar implemented in Plan 4.
// Hosts the transcriber settings surface, including the cloud ASR provider
// selector (#10147c).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AsrProviderSelector from '@/components/transcriber/AsrProviderSelector.vue'
import { useUserStore } from '@/stores/useUserStore'

const { t } = useI18n()
const settingsOpen = ref(false)

// #15758: the only setting here, the cloud ASR provider, is admin-only on the
// server (PATCH /providers) because it decides where every user's audio goes.
// A non-admin would only get a 403, so the settings surface is offered to
// admins alone.
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)
</script>
<template>
  <div class="transcriber-layout">
    <header v-if="isAdmin" class="transcriber-layout-bar">
      <button
        type="button"
        class="btn btn-sm"
        :aria-expanded="settingsOpen"
        @click="settingsOpen = !settingsOpen"
      >
        {{ settingsOpen ? t('transcriber.layout.hideSettingsButton') : t('transcriber.layout.settingsButton') }}
      </button>
    </header>

    <section
      v-if="settingsOpen"
      class="transcriber-layout-settings"
      :aria-label="t('transcriber.layout.settingsHeading')"
    >
      <h2 class="transcriber-layout-settings-heading">{{ t('transcriber.layout.settingsHeading') }}</h2>
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
