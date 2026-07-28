<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  GH#11356: Company OS company-wide Activity feed.

  Dedicated operator view over the LLC activity log (GH#8216,
  autobot-backend/llc/api/activity.py: GET /companies/{id}/activity) — a
  paginated, filterable audit trail (actor / entity / action). Company-scoped
  via :companyId so the LlcSidebar stays mounted (#10750 B3).

  NOTE: the backend exposes no activity WebSocket, so "live" is approximated
  with an opt-in polling refresh. A true push stream is a separate backend task.
-->
<template>
  <div class="activity-feed">
    <div class="feed-header">
      <h2 class="view-title">{{ $t('llc.activity.title') }}</h2>
      <div class="feed-header-actions">
        <label class="poll-toggle">
          <input type="checkbox" :checked="autoRefresh" @change="toggleAutoRefresh" />
          {{ $t('llc.activity.autoRefresh') }}
        </label>
        <button class="btn-sm" :disabled="isLoading" @click="reload">
          {{ isLoading ? $t('llc.activity.refreshing') : $t('llc.activity.refresh') }}
        </button>
      </div>
    </div>

    <div class="feed-filters">
      <label class="filter">
        <span>{{ $t('llc.activity.filterActor') }}</span>
        <select v-model="filters.actor_type" @change="applyFilters">
          <option value="">{{ $t('llc.activity.actorAll') }}</option>
          <option value="agent">{{ $t('llc.activity.actorAgent') }}</option>
          <option value="user">{{ $t('llc.activity.actorUser') }}</option>
          <option value="system">{{ $t('llc.activity.actorSystem') }}</option>
        </select>
      </label>
      <label class="filter">
        <span>{{ $t('llc.activity.filterEntity') }}</span>
        <input
          v-model.trim="filters.entity_type"
          type="text"
          :placeholder="$t('llc.activity.filterEntityPlaceholder')"
          @keyup.enter="applyFilters"
        />
      </label>
      <label class="filter">
        <span>{{ $t('llc.activity.filterAction') }}</span>
        <input
          v-model.trim="filters.action"
          type="text"
          :placeholder="$t('llc.activity.filterActionPlaceholder')"
          @keyup.enter="applyFilters"
        />
      </label>
      <button class="btn-sm" @click="applyFilters">{{ $t('llc.activity.applyFilters') }}</button>
      <button v-if="hasActiveFilters" class="btn-sm btn-ghost" @click="clearFilters">
        {{ $t('llc.activity.clearFilters') }}
      </button>
    </div>

    <div v-if="isLoading && entries.length === 0" class="state-msg">{{ $t('llc.activity.loading') }}</div>
    <div v-else-if="loadError" class="state-msg state-error">{{ loadError }}</div>
    <div v-else-if="entries.length === 0" class="state-msg">{{ $t('llc.activity.empty') }}</div>

    <ul v-else class="event-list">
      <li v-for="entry in entries" :key="entry.id" class="event-item">
        <span class="actor-badge" :class="`actor-${entry.actor_type}`">{{ actorLabel(entry.actor_type) }}</span>
        <div class="event-body">
          <span class="event-action">{{ entry.action }}</span>
          <span class="event-entity">{{ entry.entity_type }}<span class="event-entity-id" :title="entry.entity_id">#{{ shortId(entry.entity_id) }}</span></span>
          <span v-if="actorName(entry)" class="event-actor-name">· {{ actorName(entry) }}</span>
        </div>
        <time class="event-time" :title="formatDateTime(entry.occurred_at)">{{ formatTimeAgo(entry.occurred_at) }}</time>
      </li>
    </ul>

    <div v-if="entries.length > 0" class="feed-pagination">
      <span class="page-info">{{ $t('llc.activity.pageInfo', { page, total }) }}</span>
      <div class="page-buttons">
        <button class="btn-sm" :disabled="page <= 1 || isLoading" @click="goToPage(page - 1)">
          {{ $t('llc.activity.prev') }}
        </button>
        <button class="btn-sm" :disabled="!hasNext || isLoading" @click="goToPage(page + 1)">
          {{ $t('llc.activity.next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { formatDateTime, formatTimeAgo } from '@/utils/formatHelpers'
import type { components } from '@/types/generated/api'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ companyId?: string }>()

const logger = createLogger('ActivityFeedView')
const api = useApiClient()
const { t } = useI18n()

// No backend push stream exists; poll at a fixed cadence when auto-refresh is on.
const POLL_INTERVAL_MS = 15000
const PAGE_SIZE = 50

// #11367: derive from the generated OpenAPI schema so backend field changes
// surface as type errors instead of silently drifting.
type ActivityEntry = components['schemas']['ActivityLogEntry']
type ActivityResponse = components['schemas']['ActivityLogResponse']

const entries = ref<ActivityEntry[]>([])
const page = ref(1)
const total = ref(0)
const hasNext = ref(false)
const isLoading = ref(false)
const loadError = ref('')
const autoRefresh = ref(false)
const filters = ref({ actor_type: '', entity_type: '', action: '' })
let pollTimer: ReturnType<typeof setInterval> | null = null

const hasActiveFilters = computed(
  () => !!(filters.value.actor_type || filters.value.entity_type || filters.value.action),
)

function actorLabel(actorType: ActivityEntry['actor_type']) {
  return t(`llc.activity.actor${actorType.charAt(0).toUpperCase()}${actorType.slice(1)}`)
}

function actorName(entry: ActivityEntry) {
  return entry.actor_agent_id ?? entry.actor_user_id ?? ''
}

function shortId(id: string) {
  return id.length > 8 ? id.slice(0, 8) : id
}

function buildQuery() {
  const params = new URLSearchParams({ page: String(page.value), page_size: String(PAGE_SIZE) })
  if (filters.value.actor_type) params.set('actor_type', filters.value.actor_type)
  if (filters.value.entity_type) params.set('entity_type', filters.value.entity_type)
  if (filters.value.action) params.set('action', filters.value.action)
  return params.toString()
}

async function loadActivity() {
  if (!props.companyId) return
  isLoading.value = true
  loadError.value = ''
  try {
    const res = await api.get<ActivityResponse>(
      `/api/llc/companies/${props.companyId}/activity?${buildQuery()}`,
    )
    entries.value = res.items
    total.value = res.total
    hasNext.value = res.has_next
  } catch (err) {
    logger.error('Failed to load activity', err)
    loadError.value = t('llc.activity.loadFailed')
  } finally {
    isLoading.value = false
  }
}

function reload() {
  void loadActivity()
}

function applyFilters() {
  page.value = 1
  void loadActivity()
}

function clearFilters() {
  filters.value = { actor_type: '', entity_type: '', action: '' }
  applyFilters()
}

function goToPage(next: number) {
  if (next < 1) return
  page.value = next
  void loadActivity()
}

function toggleAutoRefresh(event: Event) {
  autoRefresh.value = (event.target as HTMLInputElement).checked
  if (autoRefresh.value) {
    pollTimer = setInterval(() => {
      if (page.value === 1 && !isLoading.value) void loadActivity()
    }, POLL_INTERVAL_MS)
  } else if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => void loadActivity())
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
/* Ember semantic tokens with fallbacks for non-ember themes. */
.activity-feed {
  padding: 1rem 1.25rem;
}

.feed-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.view-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.feed-header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.poll-toggle {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.feed-filters {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 0;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-default);
}

.filter {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
}

.filter input,
.filter select {
  padding: 0.375rem 0.5rem;
  font-size: 0.875rem;
  font-weight: 400;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-primary);
}

.state-msg {
  padding: 1.5rem 0;
  color: var(--text-muted);
}

.state-error {
  color: var(--color-danger);
}

.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.event-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.875rem;
}

.actor-badge {
  flex: none;
  min-width: 3.5rem;
  text-align: center;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  border-radius: 999px;
  background: var(--bg-muted, var(--actfeed-badge-neutral-bg));
  color: var(--text-secondary);
}

.actor-agent {
  background: var(--color-accent-subtle, var(--actfeed-accent-subtle));
  color: var(--color-accent-text, var(--actfeed-accent-text));
}

.actor-user {
  background: var(--color-info-subtle, var(--actfeed-info-subtle));
  color: var(--color-info-text, var(--actfeed-info-text));
}

.actor-system {
  background: var(--bg-muted, var(--actfeed-system-badge-bg));
  color: var(--text-muted);
}

.event-body {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.event-action {
  font-weight: 600;
  color: var(--text-primary);
}

.event-entity {
  color: var(--text-secondary);
}

.event-entity-id {
  font-family: var(--font-mono, monospace);
  font-size: 0.75rem;
  color: var(--text-muted);
}

.event-actor-name {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.event-time {
  flex: none;
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.feed-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.75rem;
  margin-top: 0.5rem;
}

.page-info {
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.page-buttons {
  display: flex;
  gap: 0.5rem;
}

.btn-sm {
  padding: 0.3125rem 0.75rem;
  font-size: 0.8125rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
}

.btn-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost {
  border-color: transparent;
  color: var(--color-accent-text, var(--actfeed-accent-text));
}
</style>
