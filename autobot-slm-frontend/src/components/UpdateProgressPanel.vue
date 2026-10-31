<template>
  <div v-if="active && progress" class="mt-3 rounded-md border border-gray-200 p-3 text-sm" data-testid="update-progress">
    <p class="font-medium">{{ $t('updateProgressPanel.title') }}</p>
    <p v-if="progress.play">{{ $t('updateProgressPanel.play', { name: progress.play }) }}</p>
    <p v-if="progress.task">{{ $t('updateProgressPanel.task', { name: progress.task }) }}</p>
    <p v-if="progress.last_line_at">
      {{ $t('updateProgressPanel.lastLine', { time: formatFleetDateTime(progress.last_line_at) }) }}
    </p>
    <p v-if="progress.elapsed_seconds !== null">
      {{ $t('updateProgressPanel.elapsed', { minutes: Math.floor(progress.elapsed_seconds / 60) }) }}
    </p>
    <p v-if="stateMessage" class="mt-1 font-medium" data-testid="update-progress-state">{{ $t(stateMessage) }}</p>
    <p class="mt-1 text-gray-500">{{ $t('updateProgressPanel.note') }}</p>
  </div>
</template>

<script setup lang="ts">
// #20254: what a running update is doing, from its own log, across the SLM's restart.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formatFleetDateTime } from '@/composables/useTimezone'
import slmApiClient from '@/utils/ApiClient'

interface UpdateProgress {
  state: 'waiting' | 'running' | 'quiet' | 'exited_without_recap' | 'finished' | 'unknown'
  play: string | null
  task: string | null
  last_line_at: string | null
  elapsed_seconds: number | null
}

const POLL_MS = 5000
const STATE_MESSAGES: Partial<Record<UpdateProgress['state'], string>> = {
  waiting: 'updateProgressPanel.waiting',
  quiet: 'updateProgressPanel.quiet',
  exited_without_recap: 'updateProgressPanel.exited',
  unknown: 'updateProgressPanel.unknown',
}

const props = defineProps<{ active: boolean; since?: string | null }>()
const progress = ref<UpdateProgress | null>(null)
const stateMessage = computed(() => (progress.value ? STATE_MESSAGES[progress.value.state] : undefined))
let timer: ReturnType<typeof setTimeout> | null = null

async function poll(): Promise<void> {
  try {
    const query = props.since ? `?since=${encodeURIComponent(props.since)}` : ''
    progress.value = await slmApiClient.get<UpdateProgress>(`/code-sync/update-all/progress${query}`)
  } catch {
    // The SLM is restarting, or this user may not read the log: keep what is on screen and try again.
  }
  if (props.active) timer = setTimeout(poll, POLL_MS)
}

function stop(): void {
  if (timer) clearTimeout(timer)
  timer = null
}

watch(
  () => props.active,
  (active) => {
    stop()
    if (active) void poll()
  },
  { immediate: true },
)
onBeforeUnmount(stop)
</script>
