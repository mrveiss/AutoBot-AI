<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSidebarSystemControl -- the Reload System control, moved out of ChatSidebar unchanged in
  behaviour (#18243, decision D1). Advanced (`.adv`): hidden in Minimal mode. It leaves Chat for
  the SLM console's Advanced control in step 5f (#18248); until that home exists it stays here.
-->
<template>
  <section class="adv flex shrink-0 flex-col gap-2 border-t border-[var(--aui-color-border)] p-4">
    <h3 class="m-0 text-base font-semibold text-[var(--aui-color-text)]">{{ $t('chat.sidebar.systemControl') }}</h3>
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
    <p class="m-0 text-center text-xs text-[var(--aui-color-text-muted)]">{{ $t('chat.sidebar.system') }}: {{ systemStatus }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatSidebar')
const { t } = useI18n()
const isReloading = ref(false)
const systemStatus = ref(t('status.ready'))

async function reloadSystem(): Promise<void> {
  isReloading.value = true
  systemStatus.value = t('chat.sidebar.reloading')
  try {
    const data = await ApiClient.call('post', '/api/system/reload_config')
    // The route answers { status: 'success', message, timestamp }; there is no `success` key.
    if (data?.status === 'success') {
      systemStatus.value = t('status.ready')
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
