<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Admin System Health view — surfaces the CONTENT_REACH probe (#10932).
  Shows per-source live/dead backend status from the health aggregator.
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProbeBackedHealth } from '@/composables/useProbeBackedHealth'
import { PROBE_NAMES } from '@/types/probe-names'

const { t } = useI18n()

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ContentReachHealth {
  status: string
  detail: string | undefined
  sources: Record<string, string[]>
  live: Record<string, string[]>
}

// ---------------------------------------------------------------------------
// Composable wiring
// ---------------------------------------------------------------------------

const getHealth = useProbeBackedHealth<ContentReachHealth>({
  probeName: PROBE_NAMES.CONTENT_REACH,
  buildHealthy: (probe, data) => ({
    status: probe.status ?? 'unavailable',
    detail: probe.detail,
    sources: (data.sources as Record<string, string[]>) ?? {},
    live: (data.live as Record<string, string[]>) ?? {},
  }),
  buildUnavailable: (message) => ({
    status: 'unavailable',
    detail: message,
    sources: {},
    live: {},
  }),
  errorMessage: t('admin.systemHealth.error'),
})

// ---------------------------------------------------------------------------
// Reactive state
// ---------------------------------------------------------------------------

const loading = ref(false)
const health = ref<ContentReachHealth | null>(null)

const sourceNames = computed(() => Object.keys(health.value?.sources ?? {}))
const noSources = computed(() => !loading.value && sourceNames.value.length === 0)

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

type BadgeVariant = 'green' | 'yellow' | 'red' | 'gray'

function statusBadgeClass(status: string): string {
  const variants: Record<string, BadgeVariant> = {
    ok: 'green',
    degraded: 'yellow',
    down: 'red',
  }
  const variant: BadgeVariant = variants[status] ?? 'gray'
  const map: Record<BadgeVariant, string> = {
    green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    red: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    gray: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  }
  return map[variant]
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    ok: t('admin.systemHealth.healthy'),
    degraded: t('admin.systemHealth.degraded'),
    down: t('admin.systemHealth.down'),
    unavailable: t('admin.systemHealth.unavailable'),
  }
  return map[status] ?? status
}

function isLive(source: string, backend: string): boolean {
  return (health.value?.live[source] ?? []).includes(backend)
}

// ---------------------------------------------------------------------------
// Load / refresh
// ---------------------------------------------------------------------------

async function refresh(): Promise<void> {
  loading.value = true
  health.value = await getHealth()
  loading.value = false
}

onMounted(refresh)
</script>

<template>
  <div class="p-6 max-w-4xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {{ $t('admin.systemHealth.title') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ $t('admin.systemHealth.subtitle') }}
        </p>
      </div>
      <button
        class="inline-flex items-center px-4 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        :disabled="loading"
        @click="refresh"
      >
        {{ $t('admin.systemHealth.refresh') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-16 text-gray-400 dark:text-gray-500">
      <span class="animate-spin mr-2">&#8987;</span>
      {{ $t('admin.systemHealth.loading') }}
    </div>

    <!-- Health data -->
    <template v-else-if="health">
      <!-- Overall status row -->
      <div class="flex items-start gap-4 mb-6 p-4 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
        <div class="flex-1">
          <span class="text-sm font-medium text-gray-600 dark:text-gray-400">
            {{ $t('admin.systemHealth.status') }}
          </span>
          <div class="mt-1 flex items-center gap-3">
            <span
              class="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold"
              :class="statusBadgeClass(health.status)"
            >
              {{ statusLabel(health.status) }}
            </span>
            <span v-if="health.detail" class="text-sm text-gray-500 dark:text-gray-400">
              {{ health.detail }}
            </span>
          </div>
        </div>
      </div>

      <!-- No sources empty state -->
      <div
        v-if="noSources"
        class="py-12 text-center text-gray-400 dark:text-gray-500"
      >
        {{ $t('admin.systemHealth.noSources') }}
      </div>

      <!-- Sources grid -->
      <div v-else>
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">
          {{ $t('admin.systemHealth.sources') }}
        </h2>
        <div class="space-y-4">
          <div
            v-for="source in sourceNames"
            :key="source"
            class="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4"
          >
            <div class="flex items-center justify-between mb-3">
              <span class="font-medium text-gray-900 dark:text-gray-100 capitalize">{{ source }}</span>
              <span class="text-xs text-gray-500 dark:text-gray-400">
                {{ $t('admin.systemHealth.backends') }}
              </span>
            </div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="backend in health.sources[source]"
                :key="backend"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
                :class="isLive(source, backend)
                  ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                  : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'"
              >
                <span
                  class="h-1.5 w-1.5 rounded-full"
                  :class="isLive(source, backend) ? 'bg-green-500' : 'bg-red-500'"
                />
                {{ backend }}
                <span class="sr-only">
                  {{ isLive(source, backend) ? $t('admin.systemHealth.live') : $t('admin.systemHealth.down') }}
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
