<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="slm-novnc-view view-container-full">
    <div class="slm-novnc-header">
      <HostSelector
        v-model="selectedHost"
        required-capability="vnc"
        @host-selected="onHostSelected"
      />
    </div>
    <DesktopInterface
      v-if="selectedHost"
      :key="`slm-vnc-${selectedHost.id}`"
      :host="selectedHost"
      class="slm-novnc-desktop"
    />
    <div v-else class="slm-novnc-empty">
      <Icon name="desktop" class="slm-novnc-empty-icon" />
      <p class="slm-novnc-empty-title">{{ $t('slm.novnc.selectHost') }}</p>
      <p class="slm-novnc-empty-desc">{{ $t('slm.novnc.selectHostDesc') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import type { SelectorHost } from '@/composables/useHostSelector'
import HostSelector from '@/components/ui/HostSelector.vue'
import DesktopInterface from '@/components/desktop/DesktopInterface.vue'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('SlmNoVncView')

const selectedHost = ref<SelectorHost | null>(null)

const onHostSelected = (host: SelectorHost) => {
  logger.info('VNC host selected:', { name: host.name, host: host.host })
  selectedHost.value = host
}
</script>

<style scoped>
@reference "../assets/tailwind.css";

.slm-novnc-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  @apply bg-autobot-bg-secondary;
}

.slm-novnc-header {
  @apply flex items-center gap-3 px-4 py-2 bg-autobot-bg-secondary border-b border-autobot-border text-sm;
}

.slm-novnc-desktop {
  flex: 1;
  min-height: 0;
}

.slm-novnc-empty {
  @apply flex-1 flex flex-col items-center justify-center text-autobot-text-muted;
}

.slm-novnc-empty-icon {
  @apply text-5xl mb-4 opacity-50;
}

.slm-novnc-empty-title {
  @apply text-lg mb-2;
}

.slm-novnc-empty-desc {
  @apply text-sm text-autobot-text-muted;
}
</style>
