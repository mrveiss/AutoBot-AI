<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  RumDataTables (#18277): what the backend holds, from one /rum/export read: events by type,
  sessions, and the latest events. URLs, user agents and event data are sent by browsers, so they
  are shown as text only. The export lists the latest 1000 events; the totals count every one held.
-->
<template>
  <div class="flex flex-col gap-4">
    <BaseCard :title="t(`${NS}.types.title`)">
      <BaseTable
        :columns="typeColumns" :rows="typeRows" row-key="type" :aria-label="t(`${NS}.types.title`)"
        :empty-title="t(`${NS}.types.empty`)" data-testid="slm-rum-types"
      />
    </BaseCard>

    <BaseCard :title="t(`${NS}.sessions.title`)">
      <BaseTable
        :columns="sessionColumns" :rows="sessionRows" row-key="id" :aria-label="t(`${NS}.sessions.title`)"
        :empty-title="t(`${NS}.sessions.empty`)" data-testid="slm-rum-sessions"
      />
    </BaseCard>

    <BaseCard :title="t(`${NS}.events.title`)">
      <p class="m-0 mb-3 text-sm text-(--aui-color-text-muted)" data-testid="slm-rum-events-note">
        {{ t(`${NS}.events.shown`, { shown: data.events.length, total: data.summary.total_events }) }}
      </p>
      <BaseTable
        :columns="eventColumns" :rows="eventRows" row-key="key" :aria-label="t(`${NS}.events.title`)"
        :empty-title="t(`${NS}.events.empty`)" :page-size="EVENTS_PAGE_SIZE"
        :pagination-labels="{ previous: t(`${NS}.page.previous`), next: t(`${NS}.page.next`) }"
        :pagination-label="t(`${NS}.page.label`)"
        :pagination-summary="(page: number, count: number) => t(`${NS}.page.summary`, { page, count })"
        data-testid="slm-rum-events"
      />
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseCard, BaseTable, type BaseTableColumn } from '@autobot/ui'
import { formatFleetDateTime } from '@/composables/useTimezone'
import type { RumExport } from '@/composables/useRumApi'

const NS = 'monitoring.rum'
const EVENTS_PAGE_SIZE = 25
const props = defineProps<{ data: RumExport }>()
const { t } = useI18n()

const typeColumns = computed<BaseTableColumn[]>(() => [
  { key: 'type', label: t(`${NS}.types.col.type`), monospace: true },
  { key: 'count', label: t(`${NS}.types.col.count`), numeric: true },
])
const typeRows = computed(() =>
  Object.entries(props.data.summary.event_types)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count),
)

const sessionColumns = computed<BaseTableColumn[]>(() => [
  { key: 'id', label: t(`${NS}.sessions.col.id`), monospace: true },
  { key: 'initial_url', label: t(`${NS}.sessions.col.url`), wrap: true },
  { key: 'user_agent', label: t(`${NS}.sessions.col.agent`), wrap: true },
  { key: 'event_count', label: t(`${NS}.sessions.col.events`), numeric: true },
  { key: 'start', label: t(`${NS}.sessions.col.started`) },
  { key: 'last', label: t(`${NS}.sessions.col.last`) },
])
/** Most recently active first; ISO times from one server order as strings. */
const sessionRows = computed(() =>
  Object.entries(props.data.sessions)
    .map(([id, s]) => ({ id, initial_url: s.initial_url, user_agent: s.user_agent, event_count: s.event_count, start: formatFleetDateTime(s.start_time), last: formatFleetDateTime(s.last_activity), sort: s.last_activity }))
    .sort((a, b) => b.sort.localeCompare(a.sort)),
)

const eventColumns = computed<BaseTableColumn[]>(() => [
  { key: 'at', label: t(`${NS}.events.col.at`) },
  { key: 'type', label: t(`${NS}.events.col.type`), monospace: true },
  { key: 'url', label: t(`${NS}.events.col.url`), wrap: true },
  { key: 'session', label: t(`${NS}.events.col.session`), monospace: true },
])
/** Newest first; the export lists them oldest first. */
const eventRows = computed(() =>
  [...props.data.events]
    .reverse()
    .map((e, i) => ({ key: `${e.server_timestamp}:${i}`, at: formatFleetDateTime(e.server_timestamp), type: e.type, url: e.url, session: e.sessionId })),
)
</script>
