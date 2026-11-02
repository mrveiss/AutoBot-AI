<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/** #20250: an update can succeed and still leave nodes offline; that must not read as plain success. */
import { onMounted, ref } from 'vue'
import { slmApiClient } from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { BaseAlert } from '@autobot/ui'

const logger = createLogger('UpdateNodesOfflineAlert')
const offline = ref(0)
const total = ref(0)

onMounted(async () => {
  try {
    const result: { nodes_offline: number; nodes_total: number } = await slmApiClient.get(
      '/code-sync/update-all/nodes-offline',
    )
    offline.value = result.nodes_offline
    total.value = result.nodes_total
  } catch (err) {
    logger.warn('Could not read nodes left offline by the last update', err)
  }
})
</script>

<template>
  <BaseAlert
    v-if="offline > 0"
    variant="warning"
    class="mb-6"
    :message="$t('codeSyncView.nodesOfflineAfterUpdate', { offline, total })"
  />
</template>
