<template>
  <BaseAlert v-if="visible && (progress || requestFailed)" variant="info" data-testid="update-progress">
    <template #title>{{ $t('updateProgressPanel.title') }}</template>
    <p v-if="requestFailed" data-testid="update-progress-unavailable">{{ $t('updateProgressPanel.unavailable') }}</p>
    <p v-if="progress?.play">{{ $t('updateProgressPanel.play', { name: progress.play }) }}</p>
    <p v-if="progress?.task">{{ $t('updateProgressPanel.task', { name: progress.task }) }}</p>
    <p v-if="progress?.last_line_at">
      {{ $t('updateProgressPanel.lastLine', { time: formatFleetDateTime(progress.last_line_at) }) }}
    </p>
    <p v-if="progress?.elapsed_seconds != null">
      {{ $t('updateProgressPanel.elapsed', { minutes: Math.floor(progress.elapsed_seconds / 60) }) }}
    </p>
    <p v-if="stateMessage" data-testid="update-progress-state">{{ $t(stateMessage) }}</p>
    <p v-if="runContinues">{{ $t('updateProgressPanel.note') }}</p>
  </BaseAlert>
</template>

<script setup lang="ts">
// #20254: what a running update is doing, from its own log, across the SLM's restart. It follows the
// run, not the page's job: a reload after the restart, or "Update This Server", has no job to tie to.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { BaseAlert } from '@autobot/ui'
import { formatFleetDateTime } from '@/composables/useTimezone'
import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

type UpdateProgress = components['schemas']['UpdateProgress']

const LIVE_POLL_MS = 5000
const IDLE_POLL_MS = 30000
const STATE_MESSAGES: Partial<Record<UpdateProgress['state'], string>> = {
  waiting: 'updateProgressPanel.waiting',
  quiet: 'updateProgressPanel.quiet',
  exited_without_recap: 'updateProgressPanel.exited',
  unknown: 'updateProgressPanel.unknown',
}

const props = defineProps<{ active: boolean; since?: string | null }>()
const progress = ref<UpdateProgress | null>(null)
const requestFailed = ref(false)
const runIsLive = computed(() => progress.value?.state === 'running' || progress.value?.state === 'quiet')
const visible = computed(() => props.active || runIsLive.value)
// A run that has stopped or finished does not continue in the background.
const runContinues = computed(() => {
  const state = progress.value?.state
  return state !== 'exited_without_recap' && state !== 'finished'
})
const stateMessage = computed(() => (progress.value ? STATE_MESSAGES[progress.value.state] : undefined))

// Each start takes a new generation; a request or timer from an older one does nothing when it returns.
let generation = 0
let timer: ReturnType<typeof setTimeout> | null = null

async function poll(mine: number): Promise<void> {
  try {
    const query = props.active && props.since ? `?since=${encodeURIComponent(props.since)}` : ''
    const data: UpdateProgress = await slmApiClient.get(`/code-sync/update-all/progress${query}`)
    if (mine === generation) {
      progress.value = data
      requestFailed.value = false
    }
  } catch {
    // The SLM is restarting, or this user may not read the log: keep what is on screen, say so, try again.
    if (mine === generation) requestFailed.value = true
  }
  if (mine === generation) timer = setTimeout(() => void poll(mine), visible.value ? LIVE_POLL_MS : IDLE_POLL_MS)
}

function stop(): void {
  generation += 1
  if (timer) clearTimeout(timer)
  timer = null
}

watch(
  () => props.active,
  (active) => {
    stop()
    if (active) progress.value = null // the last run's position is not this run's
    requestFailed.value = false
    void poll(generation)
  },
  { immediate: true },
)
onBeforeUnmount(stop)
</script>
