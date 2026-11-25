<template>
  <section class="flex flex-col gap-3" data-testid="audit-event-logs">
    <div class="flex items-end gap-3">
      <BaseInput
        v-model="userId"
        :label="$t('audit.eventLogs.userFilter')"
        :placeholder="$t('audit.eventLogs.userPlaceholder')"
        size="sm"
        @keyup.enter="applyFilters"
      />
      <BaseSelectMenu
        v-model="eventType"
        :options="typeOptions"
        :label="$t('audit.eventLogs.typeFilter')"
        :placeholder="$t('audit.eventLogs.allTypes')"
        size="sm"
      />
      <BaseButton size="sm" :disabled="loading" @click="applyFilters">
        {{ $t('audit.eventLogs.refresh') }}
      </BaseButton>
    </div>

    <BaseAlert v-if="failed" variant="error" :message="$t('audit.eventLogs.error')">
      <template #actions>
        <BaseButton size="sm" @click="load">{{ $t('audit.eventLogs.retry') }}</BaseButton>
      </template>
    </BaseAlert>

    <BaseTable
      v-else
      :columns="columns"
      :rows="rows"
      row-key="id"
      :caption="$t('audit.eventLogs.caption')"
      :loading="loading"
      :loading-label="$t('audit.eventLogs.loading')"
      :empty-title="$t('audit.eventLogs.empty')"
      :empty-description="$t('audit.eventLogs.emptyHint')"
    />

    <BasePagination
      v-if="!failed"
      :page="page"
      :has-next="hasNext"
      :disabled="loading"
      :labels="{ previous: $t('audit.logTable.previous'), next: $t('audit.logTable.next') }"
      :label="$t('audit.logTable.paginationAria')"
      @update:page="goToPage"
    >
      <template #summary>{{ $t('audit.logTable.pageOf', { page }) }}</template>
    </BasePagination>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseInput, BasePagination, BaseSelectMenu, BaseTable } from '@autobot/ui'
import { useAuditApi, type ComplianceEvent, type EventLogQuery } from '@/composables/useAuditApi'
import { useLatestRequest } from '@/composables/useLatestRequest'
import { formatDateTime } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'

const PAGE_SIZE = 50

// The header Auto-refresh bumps this while the tab is open; the panel reloads its applied view (#22214).
const props = defineProps<{ refreshTick?: number }>()

const { t } = useI18n()
const logger = createLogger('AuditEventLogsPanel')
const { queryEventLogs } = useAuditApi()

const userId = ref('')
const eventType = ref('')
// What the loaded rows were fetched with. Paging and retry read these, never the editable fields above.
const appliedUserId = ref('')
const appliedEventType = ref('')
const latest = useLatestRequest()
const page = ref(1)
const loading = ref(false)
const failed = ref(false)
const events = ref<ComplianceEvent[]>([])
const eventTypes = ref<string[]>([])
const hasNext = ref(false)

const columns = computed(() => [
  { key: 'time', label: t('audit.eventLogs.time') },
  { key: 'actor_id', label: t('audit.eventLogs.user') },
  { key: 'action', label: t('audit.eventLogs.event') },
  { key: 'outcome', label: t('audit.eventLogs.outcome') },
])
const rows = computed(() =>
  events.value.map((e) => ({ ...e, time: formatDateTime(new Date(e.occurred_at * 1000)) })),
)
const typeOptions = computed(() => [
  { value: '', label: t('audit.eventLogs.allTypes') },
  ...eventTypes.value.map((type) => ({ value: type, label: type })),
])

async function load() {
  const token = latest.begin()
  loading.value = true
  failed.value = false
  const query: EventLogQuery = {
    user_id: appliedUserId.value || undefined,
    event_type: appliedEventType.value || undefined,
    limit: PAGE_SIZE + 1, // one extra row says whether a next page exists (backend caps limit at 1000)
    offset: (page.value - 1) * PAGE_SIZE,
  }
  const result = await queryEventLogs(query)
  if (!latest.isCurrent(token)) return // a newer load owns the rows and the loading flag
  loading.value = false
  if (!result) {
    failed.value = true
    logger.warn('Event logs unavailable')
    return
  }
  events.value = result.events.slice(0, PAGE_SIZE)
  eventTypes.value = result.available_event_types
  hasNext.value = result.events.length > PAGE_SIZE
}

function goToPage(next: number) {
  page.value = next
  load()
}

function applyFilters() {
  appliedUserId.value = userId.value.trim()
  appliedEventType.value = eventType.value
  page.value = 1
  load()
}

watch(() => props.refreshTick, load)
onMounted(load)
</script>
