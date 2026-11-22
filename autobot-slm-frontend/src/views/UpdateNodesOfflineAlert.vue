<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/** #20250: an update can succeed and still leave nodes offline; that must not read as plain success. */
import { onMounted, ref, watch } from 'vue'
import { slmApiClient } from '@/utils/ApiClient'
import { BaseAlert, createLogger, formatDateTime } from '@autobot/ui'

const props = defineProps<{ updating?: boolean }>()

const logger = createLogger('UpdateNodesOfflineAlert')
const offline = ref(0)
const total = ref(0)
const time = ref('')

async function load(): Promise<void> {
  try {
    const result: { nodes_offline: number; nodes_total: number; run_started_at: string } = await slmApiClient.get(
      '/code-sync/update-all/nodes-offline',
    )
    offline.value = result.nodes_offline
    total.value = result.nodes_total
    time.value = formatDateTime(result.run_started_at)
  } catch (err) {
    logger.warn('Could not read nodes left offline by the last update', err)
  }
}

onMounted(load)
watch(
  () => props.updating,
  (now, was) => {
    if (was && !now) void load()
  },
)
</script>

<template>
  <BaseAlert
    v-if="offline > 0"
    variant="warning"
    class="mb-6"
    :message="$t('codeSyncView.nodesOfflineAfterUpdate', { offline, total, time })"
  />
</template>
