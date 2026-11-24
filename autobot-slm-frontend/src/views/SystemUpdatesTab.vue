<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SystemUpdatesTab - Fleet system update management (Issue #840, #1230)
 *
 * Redesigned with real package discovery via Ansible playbook.
 * Features: discover packages, summary stats, packages table with
 * multi-select, upgrade selected/all, job tracking.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, usePollingJob } from '@autobot/ui'
import { useFleetStore } from '@/stores/fleet'
import { formatFleetDateTime } from '@/composables/useTimezone'
import {
  useSystemUpdates,
  type UpdatePackage,
} from '@/composables/useSystemUpdates'
const fleetStore = useFleetStore()
const systemUpdates = useSystemUpdates()

// Local UI state
const selectedNodeFilter = ref<string>('')
const selectedPackages = ref<Set<string>>(new Set())
const cancellingJobId = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const { t } = useI18n()

const DISCOVER_POLL_INTERVAL_MS = 3000
const JOB_POLL_INTERVAL_MS = 10_000

// Computed
const filteredPackages = computed(() => {
  if (!selectedNodeFilter.value) return systemUpdates.packages.value
  return systemUpdates.packages.value.filter(
    (p) => p.node_id === selectedNodeFilter.value,
  )
})

const allSelected = computed(
  () =>
    filteredPackages.value.length > 0 &&
    filteredPackages.value.every((p) =>
      selectedPackages.value.has(p.update_id),
    ),
)

const someSelected = computed(() => selectedPackages.value.size > 0)

const nodeOptions = computed(() => {
  const nodes = fleetStore.nodeList
  return nodes.map((n) => ({
    value: n.node_id,
    label: n.hostname || n.node_id,
  }))
})

const packagesByNode = computed(() => {
  const groups: Record<
    string,
    { node_id: string; packages: UpdatePackage[] }
  > = {}
  for (const pkg of filteredPackages.value) {
    const nid = pkg.node_id || 'unknown'
    if (!groups[nid]) groups[nid] = { node_id: nid, packages: [] }
    groups[nid].packages.push(pkg)
  }
  return Object.values(groups)
})

// Actions
async function handleCheckForUpdates(): Promise<void> {
  const nodeIds = selectedNodeFilter.value
    ? [selectedNodeFilter.value]
    : undefined
  const jobId = await systemUpdates.discoverUpdates(nodeIds)
  if (jobId) {
    startDiscoverPolling(jobId)
  }
}

type DiscoverStatus = Awaited<ReturnType<typeof systemUpdates.pollDiscoverStatus>>

/** Refresh the tab once discovery finishes, and say so when it succeeded. */
async function onDiscoverDone(status: DiscoverStatus): Promise<void> {
  await Promise.all([
    systemUpdates.fetchPackages(),
    systemUpdates.fetchSummary(),
    systemUpdates.fetchJobs(),
  ]).catch(() => undefined) // each fetch reports its own failure; never unhandled out of onDone
  if (status?.status === 'completed') {
    successMessage.value = status.message || t('systemUpdatesTab.discoveryCompleted')
    setTimeout(() => {
      successMessage.value = null
    }, 5000)
  }
}

// Both pollers stop with the component's scope (#19482). pollDiscoverStatus returns
// null on a failed read rather than throwing, so discovery keeps polling through
// transient failures, as it did before.
const discoverPoller = usePollingJob((jobId) => systemUpdates.pollDiscoverStatus(jobId), {
  intervalMs: DISCOVER_POLL_INTERVAL_MS,
  maxAttempts: Infinity,
  isComplete: (status) => status?.status === 'completed' || status?.status === 'failed',
  onDone: (status) => void onDiscoverDone(status),
})

const jobPoller = usePollingJob(() => systemUpdates.fetchJobs(), {
  intervalMs: JOB_POLL_INTERVAL_MS,
  maxAttempts: Infinity,
})

function startDiscoverPolling(jobId: string): void {
  discoverPoller.start(jobId)
}

/** One job poller, whoever asks first: the watch and onMounted can both see running jobs. */
function ensureJobPolling(): void {
  if (!jobPoller.isPolling.value) jobPoller.start('')
}

function toggleSelectAll(): void {
  if (allSelected.value) {
    selectedPackages.value.clear()
  } else {
    for (const pkg of filteredPackages.value) {
      selectedPackages.value.add(pkg.update_id)
    }
  }
}

function togglePackage(updateId: string): void {
  if (selectedPackages.value.has(updateId)) {
    selectedPackages.value.delete(updateId)
  } else {
    selectedPackages.value.add(updateId)
  }
}

async function handleUpgradeSelected(): Promise<void> {
  if (!someSelected.value) return
  // Group selected by node
  const byNode: Record<string, string[]> = {}
  for (const pkg of systemUpdates.packages.value) {
    if (selectedPackages.value.has(pkg.update_id) && pkg.node_id) {
      if (!byNode[pkg.node_id]) byNode[pkg.node_id] = []
      byNode[pkg.node_id].push(pkg.update_id)
    }
  }
  for (const [nodeId, updateIds] of Object.entries(byNode)) {
    await systemUpdates.applyUpdates(nodeId, updateIds)
  }
  selectedPackages.value.clear()
  successMessage.value = t('systemUpdatesTab.upgradeJobsStarted')
  setTimeout(() => {
    successMessage.value = null
  }, 3000)
}

async function handleUpgradeAllForNode(nodeId: string): Promise<void> {
  if (!confirm(t('systemUpdatesTab.confirmUpgradeAllOnNode', { nodeId }))) return
  const ok = await systemUpdates.upgradeAll(nodeId)
  if (ok) {
    successMessage.value = t('systemUpdatesTab.upgradeAllStartedOnNode', { nodeId })
    setTimeout(() => {
      successMessage.value = null
    }, 3000)
  }
}

async function handleCancelJob(jobId: string): Promise<void> {
  if (!confirm(t('systemUpdatesTab.confirmCancelJob'))) return
  cancellingJobId.value = jobId
  const ok = await systemUpdates.cancelJob(jobId)
  if (ok) {
    successMessage.value = t('systemUpdatesTab.jobCancelled')
    setTimeout(() => {
      successMessage.value = null
    }, 3000)
  }
  cancellingJobId.value = null
}

function getStatusBadge(status: string): string {
  const map: Record<string, string> = {
    pending: 'bg-autobot-bg-tertiary text-autobot-text-secondary',
    running: 'bg-autobot-pill-info-bg text-autobot-text-primary',
    completed: 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg',
    failed: 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg',
    cancelled: 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg',
  }
  return map[status] || 'bg-autobot-bg-tertiary text-autobot-text-secondary'
}

function getSeverityBadge(severity: string): string {
  const map: Record<string, string> = {
    security: 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg',
    critical: 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg',
    standard: 'bg-autobot-bg-tertiary text-autobot-text-secondary',
  }
  return map[severity] || 'bg-autobot-bg-tertiary text-autobot-text-secondary'
}

// Watch for running jobs to start polling
watch(
  () => systemUpdates.hasRunningJobs.value,
  (hasRunning) => {
    if (hasRunning) {
      ensureJobPolling()
    } else if (jobPoller.isPolling.value) {
      jobPoller.stop()
      // Refresh packages when jobs finish
      systemUpdates.fetchPackages()
      systemUpdates.fetchSummary()
    }
  },
)

// Lifecycle
onMounted(async () => {
  await Promise.all([
    systemUpdates.fetchPackages(),
    systemUpdates.fetchJobs(),
    systemUpdates.fetchSummary(),
    fleetStore.fetchNodes(),
  ])
  // Start job polling if there are running jobs (a no-op when the watch already did)
  if (systemUpdates.hasRunningJobs.value) ensureJobPolling()
})
</script>

<template>
  <div>
    <!-- Action Bar -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-autobot-text-primary">
          {{ $t('systemUpdatesTab.systemUpdates') }}
        </h2>
        <p class="text-sm text-autobot-text-tertiary mt-1">
          {{ $t('systemUpdatesTab.discoverAndApplySystem') }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <!-- Node filter -->
        <select
          v-model="selectedNodeFilter"
          class="px-3 py-2 border border-autobot-border-strong rounded-lg text-sm
                 bg-white focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{{ $t('systemUpdatesTab.allNodes') }}</option>
          <option
            v-for="node in nodeOptions"
            :key="node.value"
            :value="node.value"
          >
            {{ node.label }}
          </option>
        </select>
        <!-- Check for Updates button -->
        <button
          @click="handleCheckForUpdates"
          :disabled="systemUpdates.isDiscovering.value"
          class="px-4 py-2 bg-autobot-primary text-autobot-text-on-primary rounded-lg
                 hover:bg-autobot-primary-hover disabled:opacity-50
                 flex items-center gap-2"
        >
          <svg
            v-if="systemUpdates.isDiscovering.value"
            class="w-4 h-4 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              class="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              stroke-width="4"
            />
            <path
              class="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0
                 12h4zm2 5.291A7.962 7.962 0 014 12H0c0
                 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          {{
            systemUpdates.isDiscovering.value
              ? $t('systemUpdatesTab.discovering')
              : $t('systemUpdatesTab.checkForUpdates')
          }}
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <BaseAlert
      v-if="systemUpdates.error.value"
      variant="error"
      class="mb-4"
      :message="systemUpdates.error.value"
      dismissible
      :dismiss-label="$t('systemUpdatesTab.dismiss')"
      @dismiss="systemUpdates.clearError()"
    />
    <BaseAlert v-if="successMessage" variant="success" size="compact" class="mb-4" :message="successMessage" />

    <!-- Discovery Progress -->
    <div
      v-if="systemUpdates.isDiscovering.value && systemUpdates.discoverStatus.value"
      class="mb-6 bg-white rounded-lg border p-4"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium text-autobot-text-secondary">
          {{ $t('systemUpdatesTab.discoveringPackages') }}
        </span>
        <span class="text-sm text-autobot-text-tertiary">{{ $t('systemUpdatesTab.value0Value1Nodes', { value0: systemUpdates.discoverStatus.value.nodes_checked, value1: systemUpdates.discoverStatus.value.total_nodes }) }}</span>
      </div>
      <div class="w-full h-2 bg-autobot-bg-active rounded-full overflow-hidden">
        <div
          class="h-full bg-autobot-primary rounded-full transition-all
                 duration-500"
          :style="{
            width: `${systemUpdates.discoverStatus.value.progress}%`,
          }"
        ></div>
      </div>
      <p class="mt-1 text-xs text-autobot-text-tertiary">
        {{ systemUpdates.discoverStatus.value.message }}
      </p>
    </div>

    <!-- Summary Stats -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('systemUpdatesTab.totalUpgradable') }}</p>
        <p class="text-2xl font-bold">
          {{ systemUpdates.updateCount.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('systemUpdatesTab.securityUpdates') }}</p>
        <p class="text-2xl font-bold text-autobot-warning">
          {{ systemUpdates.securityCount.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('systemUpdatesTab.nodesWithUpdates') }}</p>
        <p class="text-2xl font-bold text-autobot-text-link">
          {{ systemUpdates.nodesWithUpdates.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('systemUpdatesTab.lastChecked') }}</p>
        <p class="text-sm font-medium mt-1">
          {{ formatFleetDateTime(systemUpdates.lastChecked.value, '-') }}
        </p>
      </div>
    </div>

    <!-- Available Packages -->
    <div
      v-if="filteredPackages.length > 0"
      class="bg-white rounded-lg border mb-6"
    >
      <div
        class="px-4 py-3 bg-autobot-bg-secondary border-b
               flex items-center justify-between"
      >
        <h2 class="font-medium text-autobot-text-primary">{{ $t('systemUpdatesTab.availablePackagesCount', { count: filteredPackages.length }) }}</h2>
        <div class="flex items-center gap-2">
          <button
            v-if="someSelected"
            @click="handleUpgradeSelected"
            :disabled="systemUpdates.loading.value"
            class="px-3 py-1.5 text-sm bg-autobot-primary text-autobot-text-on-primary
                   rounded-lg hover:bg-autobot-primary-hover disabled:opacity-50"
          >{{ $t('systemUpdatesTab.upgradeSelectedValue0', { value0: selectedPackages.size }) }}</button>
        </div>
      </div>

      <!-- Grouped by node -->
      <div
        v-for="group in packagesByNode"
        :key="group.node_id"
        class="border-b last:border-b-0"
      >
        <!-- Node header -->
        <div
          class="px-4 py-2 bg-autobot-bg-secondary flex items-center
                 justify-between"
        >
          <span class="text-sm font-medium text-autobot-text-secondary">
            {{ group.node_id }}
            <span class="text-autobot-text-tertiary font-normal">{{ $t('systemUpdatesTab.countPackages', { count: group.packages.length }) }}</span>
          </span>
          <button
            @click="handleUpgradeAllForNode(group.node_id)"
            :disabled="systemUpdates.loading.value"
            class="px-2 py-1 text-xs bg-autobot-pill-warn-bg text-autobot-pill-warn-fg
                   rounded hover:bg-autobot-pill-warn-bg disabled:opacity-50"
          >
            {{ $t('systemUpdatesTab.upgradeAll') }}
          </button>
        </div>
        <!-- Package rows -->
        <table class="w-full">
          <thead class="sr-only">
            <tr>
              <th>{{ $t('systemUpdatesTab.select') }}</th>
              <th>{{ $t('systemUpdatesTab.package') }}</th>
              <th>{{ $t('systemUpdatesTab.version') }}</th>
              <th>{{ $t('systemUpdatesTab.severity') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-autobot-border-subtle">
            <tr
              v-for="pkg in group.packages"
              :key="pkg.update_id"
              class="hover:bg-autobot-bg-hover"
            >
              <td class="px-4 py-2 w-10">
                <input
                  type="checkbox"
                  :checked="selectedPackages.has(pkg.update_id)"
                  @change="togglePackage(pkg.update_id)"
                  class="rounded border-autobot-border-strong text-autobot-text-link
                         focus:ring-autobot-focus"
                />
              </td>
              <td class="px-4 py-2">
                <p class="text-sm font-medium text-autobot-text-primary">
                  {{ pkg.package_name }}
                </p>
              </td>
              <td class="px-4 py-2">
                <p class="text-xs text-autobot-text-tertiary">
                  {{ pkg.current_version || '?' }}
                  &rarr;
                  {{ pkg.available_version }}
                </p>
              </td>
              <td class="px-4 py-2 text-right">
                <span
                  :class="[
                    'px-2 py-0.5 text-xs rounded-full',
                    getSeverityBadge(pkg.severity),
                  ]"
                >
                  {{ pkg.severity }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- No packages message -->
    <div
      v-else-if="
        !systemUpdates.loading.value &&
        !systemUpdates.isDiscovering.value
      "
      class="bg-white rounded-lg border mb-6 p-8 text-center
             text-autobot-text-tertiary"
    >
      <p>
        {{ $t('systemUpdatesTab.noUpgradablePackagesFound') }}
      </p>
    </div>

    <!-- Select All bar -->
    <div
      v-if="filteredPackages.length > 0"
      class="flex items-center gap-3 mb-4 px-1"
    >
      <label class="flex items-center gap-2 text-sm text-autobot-text-secondary">
        <input
          type="checkbox"
          :checked="allSelected"
          @change="toggleSelectAll"
          class="rounded border-autobot-border-strong text-autobot-text-link
                 focus:ring-autobot-focus"
        />{{ $t('systemUpdatesTab.selectAllCountPackages', { count: filteredPackages.length }) }}</label>
    </div>

    <!-- Update Jobs -->
    <div class="bg-white rounded-lg border">
      <div
        class="px-4 py-3 bg-autobot-bg-secondary border-b
               flex items-center justify-between"
      >
        <h2 class="font-medium text-autobot-text-primary">{{ $t('systemUpdatesTab.updateJobs') }}</h2>
        <button
          @click="systemUpdates.fetchJobs()"
          class="text-sm text-autobot-text-link hover:underline"
        >
          {{ $t('systemUpdatesTab.refresh') }}
        </button>
      </div>
      <table v-if="systemUpdates.jobs.value.length" class="w-full">
        <thead class="bg-autobot-bg-secondary">
          <tr>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.jobID') }}
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.node') }}
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.status') }}
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.progress') }}
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.started') }}
            </th>
            <th
              class="px-4 py-3 text-right text-xs
                     font-medium text-autobot-text-tertiary uppercase"
            >
              {{ $t('systemUpdatesTab.actions') }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-autobot-border">
          <tr
            v-for="job in systemUpdates.jobs.value"
            :key="job.job_id"
            class="hover:bg-autobot-bg-hover"
          >
            <td class="px-4 py-3 text-sm font-mono text-autobot-text-secondary">
              {{ job.job_id.slice(0, 8) }}...
            </td>
            <td class="px-4 py-3 text-sm text-autobot-text-primary">
              {{ job.node_id }}
            </td>
            <td class="px-4 py-3">
              <span
                :class="[
                  'px-2 py-1 text-xs font-medium rounded-full',
                  getStatusBadge(job.status),
                ]"
              >
                {{ job.status }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div
                  class="w-24 h-2 bg-autobot-bg-active rounded-full
                         overflow-hidden"
                >
                  <div
                    class="h-full bg-autobot-primary rounded-full
                           transition-all"
                    :style="{ width: `${job.progress}%` }"
                  ></div>
                </div>
                <span class="text-xs text-autobot-text-tertiary">
                  {{ job.progress }}%
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-sm text-autobot-text-tertiary">
              {{ formatFleetDateTime(job.started_at, '-') }}
            </td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="
                  job.status === 'running' || job.status === 'pending'
                "
                @click="handleCancelJob(job.job_id)"
                :disabled="cancellingJobId === job.job_id"
                class="px-2 py-1 text-xs bg-autobot-pill-bad-bg text-autobot-pill-bad-fg
                       rounded hover:bg-autobot-pill-bad-bg disabled:opacity-50"
              >
                {{
                  cancellingJobId === job.job_id
                    ? $t('systemUpdatesTab.cancelling')
                    : $t('systemUpdatesTab.cancel')
                }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div
        v-if="!systemUpdates.jobs.value.length"
        class="p-8 text-center text-autobot-text-tertiary"
      >
        {{ $t('systemUpdatesTab.noUpdateJobsFound') }}
      </div>
    </div>
  </div>
</template>
