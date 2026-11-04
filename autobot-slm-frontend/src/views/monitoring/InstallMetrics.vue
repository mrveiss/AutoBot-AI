<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  InstallMetrics -- SLM > Monitoring > Install, admin only (#19484). The main app's own monitoring
  figures (host, services, alerts, recommendations, GPU, NPU), read from its /monitoring routes and
  polled. The SLM stands alone, so this screen has to work when the main app does not.

  States are said apart, never folded into "nothing": reading, main app not available (every read
  failed: no figures are shown, and none from an earlier reading), partly failed (the sections that
  did answer are shown, each failed one is named), read-but-empty, and ready. The WebSocket the main
  app's old reader used is not used: the SLM vhost's main-backend proxy authenticates with a request
  header, which a browser WebSocket cannot send.
-->
<template>
  <div class="flex flex-col gap-4 p-4 text-(--aui-color-text)" data-testid="slm-install-metrics">
    <header class="flex flex-wrap items-baseline gap-3">
      <h2 class="m-0 text-xl font-semibold">{{ t(`${NS}.title`) }}</h2>
      <p class="m-0 text-(--aui-color-text-muted)">{{ t(`${NS}.subtitle`) }}</p>
      <div class="ms-auto flex items-center gap-2">
        <BaseButton variant="secondary" size="sm" :loading="state === 'loading'" data-testid="slm-install-refresh" @click="restart">
          {{ t(`${NS}.refresh`) }}
        </BaseButton>
      </div>
    </header>

    <!-- Outside the state chain: polling pauses after repeated failed reads, which is exactly when the screen is on "not available". -->
    <PollingPausedAlert :poller="poller" :message="t('common.polling.paused')" :retry-label="t('common.polling.retry')" @retry="restart" />
    <p v-if="state === 'loading'" role="status" class="m-0 flex items-center gap-2 text-(--aui-color-text-muted)" data-testid="slm-install-loading">
      <BaseSpinner size="sm" />{{ t(`${NS}.loading`) }}
    </p>
    <BaseAlert
      v-else-if="state === 'unavailable'" variant="warning" data-testid="slm-install-unavailable"
      :title="t(`${NS}.unavailableTitle`)" :message="unavailableText"
    />
    <template v-else-if="reading">
      <BaseAlert
        v-for="failure in failures" :key="failure.section" variant="error" data-testid="slm-install-section-failed"
        :title="t(`${NS}.sectionFailedTitle`, { section: failure.label })" :message="failure.text"
      />
      <EmptyState
        v-if="isEmpty" data-testid="slm-install-empty"
        :title="t(`${NS}.emptyTitle`)" :description="t(`${NS}.emptyBody`)"
      />
      <template v-else>
        <InstallMetricsOverview :reading="reading" :read-at="readAt" />
        <InstallMetricsFindings :reading="reading" />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseSpinner, EmptyState, PollingPausedAlert } from '@autobot/ui'
import { autobotApiErrorMessage } from '@/composables/autobotApiError'
import { throwUnlessLoaded, useDashboardPoller } from '@/composables/useDashboardPoller'
import {
  INSTALL_METRICS_SECTIONS,
  isMainAppUnavailable,
  useInstallMetricsApi,
  type InstallMetricsReading,
} from '@/composables/useInstallMetricsApi'
import InstallMetricsFindings from '@/components/monitoring/install/InstallMetricsFindings.vue'
import InstallMetricsOverview from '@/components/monitoring/install/InstallMetricsOverview.vue'

type LoadState = 'loading' | 'ready' | 'unavailable'

const NS = 'monitoring.installMetrics'
const POLL_INTERVAL_MS = 15000
const { t } = useI18n()
const api = useInstallMetricsApi()

const state = ref<LoadState>('loading')
const reading = ref<InstallMetricsReading | null>(null)
const readAt = ref('')

/** The first failed read's own message: why the main app could not be reached. */
const unavailableText = computed(() => {
  const first = reading.value ? INSTALL_METRICS_SECTIONS.map((k) => reading.value?.[k]).find((r) => r && !r.ok) : undefined
  return autobotApiErrorMessage(first && !first.ok ? first.error : null, t(`${NS}.unavailableBody`))
})

/** One entry per read that failed while the others answered. */
const failures = computed(() => {
  const current = reading.value
  if (!current) return []
  return INSTALL_METRICS_SECTIONS.flatMap((section) => {
    const result = current[section]
    return result.ok ? [] : [{ section, label: t(`${NS}.sections.${section}`), text: autobotApiErrorMessage(result.error, t(`${NS}.sectionFailedBody`)) }]
  })
})

/** Read but empty: every route answered and none carries a figure, a service, an alert or a recommendation. */
const isEmpty = computed(() => {
  const r = reading.value
  if (!r || failures.value.length > 0) return false
  const hasHost = r.dashboard.ok && r.dashboard.data.system_metrics != null
  const hasServices = r.services.ok && r.services.data.services.length > 0
  const hasAlerts = r.alerts.ok && r.alerts.data.alerts.length > 0
  const hasRecommendations = r.recommendations.ok && r.recommendations.data.length > 0
  const hasDevice = (r.gpu.ok && r.gpu.data.available) || (r.npu.ok && r.npu.data.available)
  return !(hasHost || hasServices || hasAlerts || hasRecommendations || hasDevice)
})

/**
 * One poll. The whole reading is replaced, so a section that fails now shows as failed and
 * never as the figure it had last time. All six failing is counted as a failed poll.
 */
async function tick(): Promise<void> {
  const next = await api.readAll()
  reading.value = next
  readAt.value = new Date().toISOString()
  const down = isMainAppUnavailable(next)
  state.value = down ? 'unavailable' : 'ready'
  throwUnlessLoaded(!down)
}

const poller = useDashboardPoller(tick, POLL_INTERVAL_MS)
function restart(): void {
  // A reading already on screen stays until the new one replaces it; only an empty or down screen shows "reading".
  if (state.value !== 'ready') state.value = 'loading'
  poller.start('')
}

onMounted(restart)
</script>
