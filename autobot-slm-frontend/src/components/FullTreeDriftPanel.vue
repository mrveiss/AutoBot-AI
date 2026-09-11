<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025-2026 mrveiss
// Author: mrveiss

/**
 * FullTreeDriftPanel - #16310 owner requirement (11 Sep 2026): "We need to
 * have drift check for all the files." Renders GET /code-sync/drift/full
 * (autobot-slm-backend/api/full_tree_drift.py) -- every deployed component,
 * every file, one verdict each -- grouped/filterable by verdict so an
 * operator can tell debris (removed_from_source) from expected state
 * (build_bundle, host_state:<category>) without reading git.
 *
 * Additive to CodeSyncView's existing per-component "File Drift Check" card
 * (Issue #2834, `fetchDrift()`): that endpoint, its response shape, and this
 * panel are entirely independent, and neither one's behavior changes the
 * other's.
 *
 * `exclusions` is an aggregate {category: count} map, not a per-file list --
 * that is the backend's contract (services/full_tree_drift.py only tracks
 * per-file paths for `modified`/`removed_from_source`; `build_bundle` and
 * `host_state:*` are counted, not enumerated, since a host can legitimately
 * carry thousands of build-bundle files). The "Build bundle" / "Host state"
 * filters below show those counts, not file lists, for the same reason.
 */

import { ref, computed } from 'vue'
import { formatDateTime } from '@/composables/useTimezone'
import {
  useCodeSync,
  type FullTreeComponentDrift,
  type FullTreeFileVerdict,
} from '@/composables/useCodeSync'

// No script-side i18n needed here -- every string is rendered through the
// template's global `$t` (registered app-wide, see @/i18n/index.ts).
const codeSync = useCodeSync()

type VerdictFilter = 'all' | 'modified' | 'removed_from_source' | 'build_bundle' | 'host_state'

const VERDICT_FILTERS: readonly VerdictFilter[] = [
  'all',
  'modified',
  'removed_from_source',
  'build_bundle',
  'host_state',
]

const isChecking = ref(false)
const verdictFilter = ref<VerdictFilter>('all')

const report = computed(() => codeSync.fullTreeDriftReport.value)
const components = computed(() => report.value?.components ?? [])

function showsGroup(group: VerdictFilter): boolean {
  return verdictFilter.value === 'all' || verdictFilter.value === group
}

function filesByVerdict(component: FullTreeComponentDrift, verdict: string): FullTreeFileVerdict[] {
  return component.drifted.filter((file) => file.verdict === verdict)
}

function buildBundleCount(component: FullTreeComponentDrift): number {
  return component.exclusions.build_bundle ?? 0
}

// host_state:<category> and deploy_only:<path> are both host-owned state
// (services/full_tree_drift.py's _classify_host_state) -- grouped under the
// one "Host state" filter an operator reads as "left alone, intentionally".
function hostStateEntries(component: FullTreeComponentDrift): [string, number][] {
  return Object.entries(component.exclusions).filter(
    ([name]) => name.startsWith('host_state:') || name.startsWith('deploy_only:'),
  )
}

function isComponentClean(component: FullTreeComponentDrift): boolean {
  return (
    filesByVerdict(component, 'modified').length === 0 &&
    filesByVerdict(component, 'removed_from_source').length === 0 &&
    buildBundleCount(component) === 0 &&
    hostStateEntries(component).length === 0
  )
}

async function handleCheck(): Promise<void> {
  isChecking.value = true
  await codeSync.fetchFullTreeDrift()
  isChecking.value = false
}

function formatChecked(value: string | undefined): string {
  return value ? formatDateTime(value) : '-'
}
</script>

<template>
  <div class="bg-white rounded-lg shadow-xs border border-gray-200">
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
      <div>
        <h3 class="text-base font-semibold text-gray-900">{{ $t('fullTreeDriftPanel.title') }}</h3>
        <p class="text-xs text-gray-500">{{ $t('fullTreeDriftPanel.description') }}</p>
      </div>
      <button
        @click="handleCheck"
        :disabled="isChecking"
        class="btn btn-secondary flex items-center gap-2 text-sm"
      >
        <svg :class="['w-4 h-4', isChecking ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {{ isChecking ? $t('fullTreeDriftPanel.checking') : $t('fullTreeDriftPanel.checkAllFiles') }}
      </button>
    </div>

    <div v-if="codeSync.error.value" class="px-4 py-2 bg-red-50 border-b border-red-100 text-sm text-red-700">
      {{ codeSync.error.value }}
    </div>

    <div v-if="report" class="px-4 py-3" data-testid="full-tree-drift-report">
      <div class="flex items-center gap-3 mb-3 text-sm text-gray-500">
        <span>{{ $t('fullTreeDriftPanel.checkedAt', { value: formatChecked(report.checked_at) }) }}</span>
        <span>{{ $t('fullTreeDriftPanel.totalCompared', { count: report.total_compared }) }}</span>
        <span :class="report.total_drift > 0 ? 'text-red-700 font-medium' : 'text-green-700 font-medium'">
          {{ $t('fullTreeDriftPanel.totalDrift', { count: report.total_drift }) }}
        </span>
      </div>

      <div v-if="report.errors.length" class="mb-3 text-sm text-red-700">
        <div v-for="msg in report.errors" :key="msg">{{ msg }}</div>
      </div>

      <div class="flex flex-wrap items-center gap-2 mb-4" role="group" :aria-label="$t('fullTreeDriftPanel.filterByVerdict')">
        <button
          v-for="option in VERDICT_FILTERS"
          :key="option"
          @click="verdictFilter = option"
          :class="[
            'px-3 py-1 rounded-full text-xs font-medium border',
            verdictFilter === option
              ? 'bg-primary-600 text-white border-primary-600'
              : 'bg-white text-gray-600 border-gray-300',
          ]"
        >
          {{ $t(`fullTreeDriftPanel.filter.${option}`) }}
        </button>
      </div>

      <div v-for="component in components" :key="component.component" class="mb-5 last:mb-0" data-testid="full-tree-drift-component">
        <div class="flex items-center gap-2 mb-2">
          <h4 class="text-sm font-semibold text-gray-800">{{ component.component }}</h4>
          <span v-if="component.skipped" class="text-xs text-gray-400">{{ $t('fullTreeDriftPanel.skipped') }}</span>
          <span v-else-if="component.error" class="text-xs text-red-600">{{ component.error }}</span>
          <span v-else class="text-xs text-gray-400">{{ $t('fullTreeDriftPanel.filesCompared', { count: component.compared }) }}</span>
        </div>

        <template v-if="!component.skipped && !component.error">
          <div v-if="showsGroup('modified') && filesByVerdict(component, 'modified').length" class="mb-2">
            <div class="text-xs font-medium text-yellow-700 mb-1">{{ $t('fullTreeDriftPanel.filter.modified') }}</div>
            <ul class="text-xs font-mono text-gray-700 space-y-0.5">
              <li v-for="file in filesByVerdict(component, 'modified')" :key="file.path">{{ file.path }}</li>
            </ul>
          </div>

          <div v-if="showsGroup('removed_from_source') && filesByVerdict(component, 'removed_from_source').length" class="mb-2">
            <div class="text-xs font-medium text-red-700 mb-1">{{ $t('fullTreeDriftPanel.filter.removed_from_source') }}</div>
            <ul class="text-xs font-mono text-gray-700 space-y-0.5">
              <li v-for="file in filesByVerdict(component, 'removed_from_source')" :key="file.path">
                {{ file.path }}
                <span class="text-gray-400">{{ $t('fullTreeDriftPanel.removedAtCommit', { commit: file.detail ?? '' }) }}</span>
              </li>
            </ul>
          </div>

          <div v-if="showsGroup('build_bundle') && buildBundleCount(component) > 0" class="text-xs text-gray-500 mb-2">
            {{ $t('fullTreeDriftPanel.buildBundleCount', { count: buildBundleCount(component) }) }}
          </div>

          <div v-if="showsGroup('host_state') && hostStateEntries(component).length" class="text-xs text-gray-500">
            <div v-for="[name, count] in hostStateEntries(component)" :key="name">
              {{ $t('fullTreeDriftPanel.hostStateCategory', { category: name, count }) }}
            </div>
          </div>

          <div v-if="isComponentClean(component)" class="text-xs text-green-700">
            {{ $t('fullTreeDriftPanel.noDrift') }}
          </div>
        </template>
      </div>
    </div>

    <div v-else class="px-4 py-6 text-center text-sm text-gray-400">
      {{ $t('fullTreeDriftPanel.noReportYet') }}
    </div>
  </div>
</template>
