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

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useFleetStore } from '@/stores/fleet'
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
let discoverPollTimer: ReturnType<typeof setInterval> | null = null
let jobPollTimer: ReturnType<typeof setInterval> | null = null

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

function startDiscoverPolling(jobId: string): void {
  stopDiscoverPolling()
  discoverPollTimer = setInterval(async () => {
    const status = await systemUpdates.pollDiscoverStatus(jobId)
    if (
      status &&
      (status.status === 'completed' || status.status === 'failed')
    ) {
      stopDiscoverPolling()
      // Refresh data after discovery completes
      await Promise.all([
        systemUpdates.fetchPackages(),
        systemUpdates.fetchSummary(),
        systemUpdates.fetchJobs(),
      ])
      if (status.status === 'completed') {
        successMessage.value = status.message || 'Discovery completed'
        setTimeout(() => {
          successMessage.value = null
        }, 5000)
      }
    }
  }, 3000)
}

function stopDiscoverPolling(): void {
  if (discoverPollTimer) {
    clearInterval(discoverPollTimer)
    discoverPollTimer = null
  }
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
  successMessage.value = 'Upgrade jobs started'
  setTimeout(() => {
    successMessage.value = null
  }, 3000)
}

async function handleUpgradeAllForNode(nodeId: string): Promise<void> {
  if (!confirm(`Upgrade ALL packages on ${nodeId}?`)) return
  const ok = await systemUpdates.upgradeAll(nodeId)
  if (ok) {
    successMessage.value = `Upgrade all started for ${nodeId}`
    setTimeout(() => {
      successMessage.value = null
    }, 3000)
  }
}

async function handleCancelJob(jobId: string): Promise<void> {
  if (!confirm('Cancel this update job?')) return
  cancellingJobId.value = jobId
  const ok = await systemUpdates.cancelJob(jobId)
  if (ok) {
    successMessage.value = 'Job cancelled'
    setTimeout(() => {
      successMessage.value = null
    }, 3000)
  }
  cancellingJobId.value = null
}

function getStatusBadge(status: string): string {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-yellow-100 text-yellow-700',
  }
  return map[status] || 'bg-gray-100 text-gray-700'
}

function getSeverityBadge(severity: string): string {
  const map: Record<string, string> = {
    security: 'bg-orange-100 text-orange-700',
    critical: 'bg-red-100 text-red-700',
    standard: 'bg-gray-100 text-gray-600',
  }
  return map[severity] || 'bg-gray-100 text-gray-600'
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

// Watch for running jobs to start polling
watch(
  () => systemUpdates.hasRunningJobs.value,
  (hasRunning) => {
    if (hasRunning && !jobPollTimer) {
      jobPollTimer = setInterval(() => {
        systemUpdates.fetchJobs()
      }, 10000)
    } else if (!hasRunning && jobPollTimer) {
      clearInterval(jobPollTimer)
      jobPollTimer = null
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
  // Start job polling if there are running jobs
  if (systemUpdates.hasRunningJobs.value) {
    jobPollTimer = setInterval(() => {
      systemUpdates.fetchJobs()
    }, 10000)
  }
})

onUnmounted(() => {
  stopDiscoverPolling()
  if (jobPollTimer) {
    clearInterval(jobPollTimer)
    jobPollTimer = null
  }
})
</script>

<template>
  <div>
    <!-- Action Bar -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">
          System Updates
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          Discover and apply system package updates across the fleet
        </p>
      </div>
      <div class="flex items-center gap-3">
        <!-- Node filter -->
        <select
          v-model="selectedNodeFilter"
          class="px-3 py-2 border border-gray-300 rounded-lg text-sm
                 bg-white focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Nodes</option>
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
          class="px-4 py-2 bg-blue-600 text-white rounded-lg
                 hover:bg-blue-700 disabled:opacity-50
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
              ? 'Discovering...'
              : 'Check for Updates'
          }}
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <div
      v-if="systemUpdates.error.value"
      class="mb-4 p-3 bg-red-50 border border-red-200
             rounded-lg text-red-700 text-sm"
    >
      {{ systemUpdates.error.value }}
      <button
        @click="systemUpdates.clearError()"
        class="ml-2 underline"
      >
        Dismiss
      </button>
    </div>
    <div
      v-if="successMessage"
      class="mb-4 p-3 bg-green-50 border border-green-200
             rounded-lg text-green-700 text-sm"
    >
      {{ successMessage }}
    </div>

    <!-- Discovery Progress -->
    <div
      v-if="systemUpdates.isDiscovering.value && systemUpdates.discoverStatus.value"
      class="mb-6 bg-white rounded-lg border p-4"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium text-gray-700">
          Discovering packages...
        </span>
        <span class="text-sm text-gray-500">
          {{ systemUpdates.discoverStatus.value.nodes_checked }} /
          {{ systemUpdates.discoverStatus.value.total_nodes }} nodes
        </span>
      </div>
      <div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          class="h-full bg-blue-600 rounded-full transition-all
                 duration-500"
          :style="{
            width: `${systemUpdates.discoverStatus.value.progress}%`,
          }"
        ></div>
      </div>
      <p class="mt-1 text-xs text-gray-500">
        {{ systemUpdates.discoverStatus.value.message }}
      </p>
    </div>

    <!-- Summary Stats -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Total Upgradable</p>
        <p class="text-2xl font-bold">
          {{ systemUpdates.updateCount.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Security Updates</p>
        <p class="text-2xl font-bold text-orange-600">
          {{ systemUpdates.securityCount.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Nodes with Updates</p>
        <p class="text-2xl font-bold text-blue-600">
          {{ systemUpdates.nodesWithUpdates.value }}
        </p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Last Checked</p>
        <p class="text-sm font-medium mt-1">
          {{ formatDate(systemUpdates.lastChecked.value) }}
        </p>
      </div>
    </div>

    <!-- Available Packages -->
    <div
      v-if="filteredPackages.length > 0"
      class="bg-white rounded-lg border mb-6"
    >
      <div
        class="px-4 py-3 bg-gray-50 border-b
               flex items-center justify-between"
      >
        <h2 class="font-medium text-gray-900">
          Available Packages ({{ filteredPackages.length }})
        </h2>
        <div class="flex items-center gap-2">
          <button
            v-if="someSelected"
            @click="handleUpgradeSelected"
            :disabled="systemUpdates.loading.value"
            class="px-3 py-1.5 text-sm bg-blue-600 text-white
                   rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            Upgrade Selected ({{ selectedPackages.size }})
          </button>
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
          class="px-4 py-2 bg-gray-50 flex items-center
                 justify-between"
        >
          <span class="text-sm font-medium text-gray-700">
            {{ group.node_id }}
            <span class="text-gray-400 font-normal">
              ({{ group.packages.length }} packages)
            </span>
          </span>
          <button
            @click="handleUpgradeAllForNode(group.node_id)"
            :disabled="systemUpdates.loading.value"
            class="px-2 py-1 text-xs bg-orange-100 text-orange-700
                   rounded hover:bg-orange-200 disabled:opacity-50"
          >
            Upgrade All
          </button>
        </div>
        <!-- Package rows -->
        <table class="w-full">
          <thead class="sr-only">
            <tr>
              <th>Select</th>
              <th>Package</th>
              <th>Version</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr
              v-for="pkg in group.packages"
              :key="pkg.update_id"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-2 w-10">
                <input
                  type="checkbox"
                  :checked="selectedPackages.has(pkg.update_id)"
                  @change="togglePackage(pkg.update_id)"
                  class="rounded border-gray-300 text-blue-600
                         focus:ring-blue-500"
                />
              </td>
              <td class="px-4 py-2">
                <p class="text-sm font-medium text-gray-900">
                  {{ pkg.package_name }}
                </p>
              </td>
              <td class="px-4 py-2">
                <p class="text-xs text-gray-500">
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
             text-gray-500"
    >
      <p>
        No upgradable packages found. Click "Check for Updates" to
        discover available packages.
      </p>
    </div>

    <!-- Select All bar -->
    <div
      v-if="filteredPackages.length > 0"
      class="flex items-center gap-3 mb-4 px-1"
    >
      <label class="flex items-center gap-2 text-sm text-gray-600">
        <input
          type="checkbox"
          :checked="allSelected"
          @change="toggleSelectAll"
          class="rounded border-gray-300 text-blue-600
                 focus:ring-blue-500"
        />
        Select all {{ filteredPackages.length }} packages
      </label>
    </div>

    <!-- Update Jobs -->
    <div class="bg-white rounded-lg border">
      <div
        class="px-4 py-3 bg-gray-50 border-b
               flex items-center justify-between"
      >
        <h2 class="font-medium text-gray-900">Update Jobs</h2>
        <button
          @click="systemUpdates.fetchJobs()"
          class="text-sm text-blue-600 hover:underline"
        >
          Refresh
        </button>
      </div>
      <table v-if="systemUpdates.jobs.value.length" class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-gray-500 uppercase"
            >
              Job ID
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-gray-500 uppercase"
            >
              Node
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-gray-500 uppercase"
            >
              Status
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-gray-500 uppercase"
            >
              Progress
            </th>
            <th
              class="px-4 py-3 text-left text-xs
                     font-medium text-gray-500 uppercase"
            >
              Started
            </th>
            <th
              class="px-4 py-3 text-right text-xs
                     font-medium text-gray-500 uppercase"
            >
              Actions
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr
            v-for="job in systemUpdates.jobs.value"
            :key="job.job_id"
            class="hover:bg-gray-50"
          >
            <td class="px-4 py-3 text-sm font-mono text-gray-600">
              {{ job.job_id.slice(0, 8) }}...
            </td>
            <td class="px-4 py-3 text-sm text-gray-900">
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
                  class="w-24 h-2 bg-gray-200 rounded-full
                         overflow-hidden"
                >
                  <div
                    class="h-full bg-blue-600 rounded-full
                           transition-all"
                    :style="{ width: `${job.progress}%` }"
                  ></div>
                </div>
                <span class="text-xs text-gray-500">
                  {{ job.progress }}%
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-sm text-gray-500">
              {{ formatDate(job.started_at) }}
            </td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="
                  job.status === 'running' || job.status === 'pending'
                "
                @click="handleCancelJob(job.job_id)"
                :disabled="cancellingJobId === job.job_id"
                class="px-2 py-1 text-xs bg-red-100 text-red-700
                       rounded hover:bg-red-200 disabled:opacity-50"
              >
                {{
                  cancellingJobId === job.job_id
                    ? 'Cancelling...'
                    : 'Cancel'
                }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div
        v-if="!systemUpdates.jobs.value.length"
        class="p-8 text-center text-gray-500"
      >
        No update jobs found
      </div>
    </div>
  </div>
</template>
