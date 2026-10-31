<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  SharedLinksView — operator cross-user view of all active shared chat links
  (GH#8996, AC4). Migrated from the user frontend into the /slm operator console
  as the first slice of umbrella #10488 Workstream A.

  Read-only table listing every active, non-expired shared link with its owner,
  session, timestamps, and password-protection state. Calls the main AutoBot
  backend via useAutobotApi (nginx-proxied at /autobot-api -> backend /api).
-->
<template>
  <div class="p-6">
    <!-- Page header -->
    <div class="flex items-start justify-between mb-6">
      <div>
        <h2 class="text-2xl font-bold text-gray-900 dark:text-white">
          {{ $t('sharedLinksView.title') }}
        </h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ $t('sharedLinksView.subtitle') }}
        </p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        :disabled="loading"
        @click="fetchLinks()"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': loading }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {{ $t('sharedLinksView.refresh') }}
      </button>
    </div>

    <!-- Error banner -->
    <div
      v-if="error"
      class="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-error-500/10 border border-error-500/30 text-error-500"
      role="alert"
    >
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span class="flex-1">{{ error }}</span>
      <button
        type="button"
        class="p-1 hover:opacity-70"
        :aria-label="$t('sharedLinksView.dismiss')"
        @click="error = null"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Loading state -->
    <div
      v-if="loading && links.length === 0"
      class="flex flex-col items-center gap-3 py-12 text-gray-500 dark:text-gray-400"
    >
      <svg class="w-6 h-6 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
      {{ $t('sharedLinksView.loading') }}
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!loading && links.length === 0"
      class="flex flex-col items-center gap-3 py-12 text-gray-500 dark:text-gray-400"
    >
      <svg class="w-8 h-8 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 01-5.656-5.656l1.5-1.5m6.328-1.328a4 4 0 010-5.656l3-3a4 4 0 015.656 5.656l-1.5 1.5" />
      </svg>
      <p>{{ $t('sharedLinksView.empty') }}</p>
    </div>

    <!-- Links table -->
    <div v-else class="overflow-hidden">
      <BaseTable
        :columns="columns"
        :rows="rows"
        :caption="$t('sharedLinksView.tableCaption')"
        size="compact"
      >
        <template #cell-session_id="{ value }">
          <code class="text-xs">{{ value }}</code>
        </template>
        <template #cell-has_password="{ value }">
          <BaseBadge size="sm" :variant="value ? 'success' : 'neutral'">
            {{ value ? $t('sharedLinksView.protected') : $t('sharedLinksView.open') }}
          </BaseBadge>
        </template>
        <template #footer>
          <p class="text-xs text-right">{{ $t('sharedLinksView.countHint', { count }) }}</p>
        </template>
      </BaseTable>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseTable, type BaseTableColumn } from '@autobot/ui'
import { useAutobotApi, type SharedLinkAdminItem } from '@/composables/useAutobotApi'
import { createLogger } from '@/utils/debugUtils'
import { createDateFormatter } from '@/utils/formatHelpers'

const logger = createLogger('SharedLinksView')
const { t } = useI18n()
const api = useAutobotApi()

const links = ref<SharedLinkAdminItem[]>([])
const count = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

// BaseTable rows are plain records; the API interface carries no index signature.
const rows = computed(() => links.value.map((link) => ({ ...link })))

const columns = computed<BaseTableColumn[]>(() => [
  { key: 'owner', label: t('sharedLinksView.colOwner') },
  { key: 'session_id', label: t('sharedLinksView.colSession') },
  { key: 'created_at', label: t('sharedLinksView.colCreated'), formatter: (v) => formatDate(String(v)) },
  {
    key: 'expires_at',
    label: t('sharedLinksView.colExpires'),
    formatter: (v) => (v ? formatDate(String(v)) : t('sharedLinksView.never')),
  },
  { key: 'has_password', label: t('sharedLinksView.colPassword') },
])

const formatDate = createDateFormatter()

async function fetchLinks(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const response = await api.getSharedLinksAdmin()
    links.value = response.data?.links ?? []
    count.value = response.data?.count ?? links.value.length
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load shared links'
    logger.error('Failed to fetch shared links', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchLinks())
</script>
