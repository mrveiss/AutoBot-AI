<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  RumMonitor -- SLM > Monitoring > Real user monitoring, admin only (#18277). What the main
  backend's /rum routes hold: the collection switch (POST /config to enable, POST /disable), the
  counts from /status, the events, sessions and event types from /export, and "Clear" behind a
  confirmation (POST /clear).

  Said apart, never folded into "nothing": reading, failed, collecting-but-empty and
  switched-off-and-empty. Events live in the backend's memory, so a restart empties them.
-->
<template>
  <div class="flex flex-col gap-4 p-4 text-(--aui-color-text)" data-testid="slm-rum">
    <header class="flex flex-wrap items-baseline gap-3">
      <h2 class="m-0 text-xl font-semibold">{{ t(`${NS}.title`) }}</h2>
      <p class="m-0 text-(--aui-color-text-muted)">{{ t(`${NS}.subtitle`) }}</p>
      <BaseButton class="ms-auto" variant="secondary" size="sm" :loading="state === 'loading'" data-testid="slm-rum-refresh" @click="load">
        {{ t(`${NS}.refresh`) }}
      </BaseButton>
    </header>

    <BaseAlert v-if="notice" :variant="notice.variant" :message="notice.text" dismissible :dismiss-label="t(`${NS}.dismiss`)" data-testid="slm-rum-notice" @dismiss="notice = null" />

    <p v-if="state === 'loading' && !status" role="status" class="m-0 flex items-center gap-2 text-(--aui-color-text-muted)" data-testid="slm-rum-loading">
      <BaseSpinner size="sm" />{{ t(`${NS}.loading`) }}
    </p>
    <BaseAlert v-else-if="state === 'error' || !status" variant="error" :title="t(`${NS}.errorTitle`)" :message="errorText" data-testid="slm-rum-error" />

    <template v-else>
      <BaseCard :title="t(`${NS}.collection.title`)" data-testid="slm-rum-collection">
        <div class="flex flex-wrap items-center gap-3">
          <BaseSwitch :model-value="status.enabled" :label="t(`${NS}.collection.switch`)" :disabled="toggling" data-testid="slm-rum-switch" @change="setEnabled" />
          <span>{{ t(`${NS}.collection.switch`) }}</span>
          <BaseBadge :variant="status.enabled ? 'success' : 'neutral'" size="sm" data-testid="slm-rum-state">{{ t(`${NS}.collection.${status.enabled ? 'on' : 'off'}`) }}</BaseBadge>
        </div>
        <p class="m-0 mt-3 text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.collection.memoryNote`) }}</p>
        <dl class="m-0 mt-4 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
          <div v-for="key in STAT_KEYS" :key="key" :data-testid="`slm-rum-stat-${key}`">
            <dt class="text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.stat.${key}`) }}</dt>
            <dd class="m-0 text-lg font-semibold tabular-nums">{{ status.statistics[key] }}</dd>
          </div>
        </dl>
      </BaseCard>

      <BaseAlert v-if="detailError" variant="warning" :title="t(`${NS}.detailFailedTitle`)" :message="detailError" data-testid="slm-rum-detail-error" />
      <EmptyState
        v-else-if="isEmpty" data-testid="slm-rum-empty"
        :title="t(`${NS}.${status.enabled ? 'emptyOnTitle' : 'emptyOffTitle'}`)" :description="t(`${NS}.${status.enabled ? 'emptyOnBody' : 'emptyOffBody'}`)"
      />
      <RumDataTables v-else-if="exported" :data="exported" />

      <BaseCard :title="t(`${NS}.settings.title`)" data-testid="slm-rum-settings">
        <dl class="m-0 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
          <div v-for="[key, value] in settingRows" :key="key" :data-testid="`slm-rum-setting-${key}`">
            <dt class="text-sm text-(--aui-color-text-muted)">{{ settingLabel(key) }}</dt>
            <dd class="m-0 tabular-nums">{{ settingValue(value) }}</dd>
          </div>
        </dl>
      </BaseCard>

      <BaseCard :title="t(`${NS}.clear.title`)" data-testid="slm-rum-danger">
        <p class="m-0 mb-3 text-(--aui-color-text-muted)">{{ t(`${NS}.clear.body`) }}</p>
        <BaseButton variant="error" :disabled="held === 0" data-testid="slm-rum-clear" @click="confirmOpen = true">{{ t(`${NS}.clear.button`) }}</BaseButton>
      </BaseCard>
    </template>

    <BaseModal v-model="confirmOpen" :title="t(`${NS}.clear.confirmTitle`)" size="sm" :close-label="t('ui.modal.closeDialog')">
      <p class="m-0" data-testid="slm-rum-confirm-body">{{ t(`${NS}.clear.confirmBody`, { events: status?.statistics.total_events ?? 0, sessions: status?.statistics.total_sessions ?? 0 }) }}</p>
      <template #actions>
        <BaseButton variant="secondary" data-testid="slm-rum-confirm-cancel" @click="confirmOpen = false">{{ t(`${NS}.clear.cancel`) }}</BaseButton>
        <BaseButton variant="error" :loading="clearing" data-testid="slm-rum-confirm-clear" @click="clearAll">{{ t(`${NS}.clear.confirm`) }}</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, BaseModal, BaseSpinner, BaseSwitch, EmptyState } from '@autobot/ui'
import { autobotApiErrorMessage } from '@/composables/autobotApiError'
import { useRumApi, type RumExport, type RumStatistics, type RumStatus } from '@/composables/useRumApi'
import RumDataTables from '@/components/monitoring/rum/RumDataTables.vue'

type LoadState = 'loading' | 'ready' | 'error'
interface Notice { variant: 'success' | 'error'; text: string }

const NS = 'monitoring.rum'
const STAT_KEYS: (keyof RumStatistics)[] = ['total_events', 'total_sessions', 'active_sessions', 'events_today']
const { t, te } = useI18n()
const api = useRumApi()

const state = ref<LoadState>('loading')
const errorText = ref('')
const status = ref<RumStatus | null>(null)
const exported = ref<RumExport | null>(null)
const detailError = ref('')
const notice = ref<Notice | null>(null)
const toggling = ref(false)
const confirmOpen = ref(false)
const clearing = ref(false)

/** Events and sessions the backend holds, from the always-readable /status. */
const held = computed(() => (status.value ? status.value.statistics.total_events + status.value.statistics.total_sessions : 0))
const isEmpty = computed(() => held.value === 0)
const settingRows = computed(() => Object.entries(status.value?.config ?? {}))

async function loadDetail(): Promise<void> {
  detailError.value = ''
  exported.value = null
  if (isEmpty.value) return
  try {
    exported.value = await api.exportData()
  } catch (e) {
    detailError.value = autobotApiErrorMessage(e, t(`${NS}.detailFailedBody`))
  }
}

async function load(): Promise<void> {
  state.value = 'loading'
  try {
    status.value = await api.getStatus()
  } catch (e) {
    errorText.value = autobotApiErrorMessage(e, t(`${NS}.errorBody`))
    state.value = 'error'
    return
  }
  await loadDetail()
  state.value = 'ready'
}

/** The setting's name in words; a setting this screen has no word for shows the backend's own key. */
const settingLabel = (key: string): string => (te(`${NS}.settings.label.${key}`) ? t(`${NS}.settings.label.${key}`) : key)
const settingValue = (value: unknown): string => (typeof value === 'boolean' ? t(`${NS}.${value ? 'yes' : 'no'}`) : String(value))

/** Runs a write, says its outcome, then re-reads so the screen shows what the backend now holds. */
async function act<R>(write: () => Promise<R>, okText: (result: R) => string, failedText: string): Promise<void> {
  notice.value = null
  try {
    notice.value = { variant: 'success', text: okText(await write()) }
  } catch (e) {
    notice.value = { variant: 'error', text: autobotApiErrorMessage(e, failedText) }
    return
  }
  await load()
}

async function setEnabled(next: boolean): Promise<void> {
  if (toggling.value || !status.value) return
  toggling.value = true
  const current = status.value.config
  await act(
    () => (next ? api.enable(current) : api.disable()),
    () => t(`${NS}.collection.${next ? 'enabledOk' : 'disabledOk'}`),
    t(`${NS}.collection.${next ? 'enableFailed' : 'disableFailed'}`),
  )
  toggling.value = false
}

async function clearAll(): Promise<void> {
  if (clearing.value) return
  clearing.value = true
  await act(
    api.clear,
    (r) => t(`${NS}.clear.done`, { events: r.events_cleared, sessions: r.sessions_cleared }),
    t(`${NS}.clear.failed`),
  )
  clearing.value = false
  confirmOpen.value = false
}

onMounted(load)
</script>
