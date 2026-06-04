<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!--
  LoadingOverlay — subtle loading indicator on top of existing content.
  Shows slot content always; adds a pulsing overlay badge when :loading is true.
  Does not replace content or block interaction.

  Use when data is refreshing and existing content should remain visible.
  See #6698 for the migration rationale.
-->
<template>
  <div class="loading-overlay-wrapper" :class="{ 'content-refreshing': loading }">
    <slot />
    <div v-if="loading" class="overlay-indicator" role="status" aria-live="polite" aria-atomic="true">
      <div class="overlay-pulse"></div>
      <span class="overlay-text">{{ t('ui.unifiedLoading.updating') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{ loading?: boolean }>()
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.loading-overlay-wrapper {
  @apply relative h-full flex flex-col;
  transition: opacity var(--duration-200) var(--ease-out);
}

.content-refreshing {
  @apply opacity-75;
}

.overlay-indicator {
  @apply absolute top-4 right-4 flex items-center gap-2 bg-autobot-bg-card px-3 py-1.5 rounded-full shadow-sm;
  opacity: 0.9;
}

.overlay-pulse {
  @apply w-2 h-2 rounded-full animate-pulse;
  background: var(--color-primary);
}

.overlay-text {
  @apply text-sm text-autobot-text-secondary;
}
</style>
