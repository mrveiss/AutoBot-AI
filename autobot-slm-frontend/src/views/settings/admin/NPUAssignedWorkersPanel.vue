<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/** #19706: nodes assigned npu-worker in the SLM that aren't paired yet, for an admin to pair. */
import { onMounted, ref } from 'vue'
import { createAutobotBackendClient, useAutobotApi } from '@/composables/useAutobotApi'
import { BaseAlert, BaseButton } from '@autobot/ui'

interface AssignedWorker { url: string; hostname: string }

const emit = defineEmits<{ paired: [] }>()
const api = useAutobotApi()
const client = createAutobotBackendClient()
const workers = ref<AssignedWorker[]>([])
const readFailed = ref(false)
const pairFailed = ref('')
const pairing = ref('')

async function load(): Promise<void> {
  try {
    const response: { workers: AssignedWorker[] } = await client.get('/npu/assigned-unpaired-workers')
    workers.value = response.workers
    readFailed.value = false
  } catch {
    readFailed.value = true
  }
}

async function pair(worker: AssignedWorker): Promise<void> {
  pairing.value = worker.url
  pairFailed.value = ''
  try {
    await api.pairNPUWorker({ url: worker.url, name: worker.hostname, enabled: true })
    await load()
    emit('paired')
  } catch {
    pairFailed.value = worker.hostname
  } finally {
    pairing.value = ''
  }
}

onMounted(load)
</script>

<template>
  <BaseAlert
    v-if="readFailed"
    variant="warning"
    :message="$t('settings.admin.nPUWorkersSettings.assignedReadFailed')"
  />
  <BaseAlert
    v-if="pairFailed"
    variant="error"
    :message="$t('settings.admin.nPUWorkersSettings.assignedPairFailed', { hostname: pairFailed })"
  />
  <BaseAlert
    v-for="worker in workers"
    :key="worker.url"
    variant="info"
    :message="$t('settings.admin.nPUWorkersSettings.assignedNotPaired', { hostname: worker.hostname })"
  >
    <template #actions>
      <BaseButton size="sm" :loading="pairing === worker.url" @click="pair(worker)">
        {{ $t('settings.admin.nPUWorkersSettings.pairWorker') }}
      </BaseButton>
    </template>
  </BaseAlert>
</template>
