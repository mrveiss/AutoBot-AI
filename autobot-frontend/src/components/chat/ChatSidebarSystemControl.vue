<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSidebarSystemControl -- the Reload System control, moved out of ChatSidebar unchanged in
  behaviour (#18243, decision D1). Advanced (`.adv`): hidden in Minimal mode. It leaves Chat for
  the SLM console's Advanced control in step 5f (#18248); until that home exists it stays here.
-->
<template>
  <section class="adv chat-system-control">
    <h3 class="chat-system-control__title">{{ $t('chat.sidebar.systemControl') }}</h3>
    <BaseButton
      block
      size="sm"
      :loading="isReloading"
      :aria-label="$t('chat.sidebar.reloadSystem')"
      @click="reloadSystem"
    >
      <template #icon-left><Icon name="sync" /></template>
      {{ isReloading ? $t('chat.sidebar.reloading') : $t('chat.sidebar.reloadSystem') }}
    </BaseButton>
    <p class="chat-system-control__status">{{ $t('chat.sidebar.system') }}: {{ systemStatus }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatSidebar')
const { t } = useI18n()
const isReloading = ref(false)
const systemStatus = ref(t('status.ready'))

async function reloadSystem(): Promise<void> {
  isReloading.value = true
  systemStatus.value = t('chat.sidebar.reloading')
  try {
    const response = await ApiClient.post<unknown>(`${getApiBase()}/system/reload_config`)
    const data = await (response as { json: () => Promise<Record<string, unknown>> }).json()
    if (data && data.success) {
      systemStatus.value = t('status.ready')
      if (data.reloaded_components) logger.debug('Reloaded components:', data.reloaded_components)
      return
    }
    systemStatus.value = t('common.error')
    logger.error('System reload failed:', data?.message || 'Unknown error')
  } catch (error) {
    systemStatus.value = t('common.error')
    logger.error('System reload failed:', error)
  } finally {
    isReloading.value = false
  }
}
</script>

<style scoped>
.chat-system-control {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-2);
  flex-shrink: 0;
  padding: var(--aui-space-4);
  border-top: 1px solid var(--aui-color-border);
}

.chat-system-control__title {
  margin: 0;
  font-size: var(--aui-text-base);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.chat-system-control__status {
  margin: 0;
  text-align: center;
  font-size: var(--aui-text-xs);
  color: var(--aui-color-text-muted);
}
</style>
