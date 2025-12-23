<template>
  <div class="infrastructure-manager view-container-flex bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Infrastructure Management</h1>
          <p class="text-sm text-gray-600 mt-1">Manage hosts and deploy configurations with Ansible</p>
        </div>
        <div class="flex items-center space-x-3">
          <button
            @click="refreshHosts"
            :disabled="isLoading"
            class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              :class="{ 'animate-spin': isLoading }"
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            Refresh
          </button>
          <button
            @click="showAddHostModal = true"
            class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
            </svg>
            Add Host
          </button>
        </div>
      </div>

      <!-- Stats Bar -->
      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div class="bg-gray-50 rounded-lg px-4 py-3 border border-gray-200">
          <div class="text-sm font-medium text-gray-600">Total Hosts</div>
          <div class="text-2xl font-bold text-gray-900">{{ hosts.length }}</div>
        </div>
        <div class="bg-green-50 rounded-lg px-4 py-3 border border-green-200">
          <div class="text-sm font-medium text-green-600">Active</div>
          <div class="text-2xl font-bold text-green-900">{{ activeHosts.length }}</div>
        </div>
        <div class="bg-yellow-50 rounded-lg px-4 py-3 border border-yellow-200">
          <div class="text-sm font-medium text-yellow-600">Pending</div>
          <div class="text-2xl font-bold text-yellow-900">{{ pendingHosts.length }}</div>
        </div>
        <div class="bg-red-50 rounded-lg px-4 py-3 border border-red-200">
          <div class="text-sm font-medium text-red-600">Errors</div>
          <div class="text-2xl font-bold text-red-900">{{ errorHosts.length }}</div>
        </div>
      </div>
    </div>

    <!-- View Toggle -->
    <div class="bg-white border-b border-gray-200 px-6 py-3">
      <div class="flex items-center space-x-4">
        <span class="text-sm font-medium text-gray-700">View:</span>
        <button
          @click="viewMode = 'grid'"
          :class="{
            'bg-indigo-100 text-indigo-700': viewMode === 'grid',
            'text-gray-600 hover:bg-gray-100': viewMode !== 'grid'
          }"
          class="px-3 py-1 text-sm font-medium rounded-md transition-colors duration-200"
        >
          Grid
        </button>
        <button
          @click="viewMode = 'table'"
          :class="{
            'bg-indigo-100 text-indigo-700': viewMode === 'table',
            'text-gray-600 hover:bg-gray-100': viewMode !== 'table'
          }"
          class="px-3 py-1 text-sm font-medium rounded-md transition-colors duration-200"
        >
          Table
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="flex-1 overflow-y-auto px-6 py-6">
      <!-- Loading State -->
      <div v-if="isLoading && hosts.length === 0" class="flex items-center justify-center h-64">
        <div class="text-center">
          <svg class="animate-spin h-12 w-12 mx-auto text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p class="mt-4 text-gray-600">Loading hosts...</p>
        </div>
      </div>

      <!-- Empty State -->
      <EmptyState
        v-else-if="hosts.length === 0"
        icon="fas fa-server"
        title="No hosts configured"
        message="Get started by adding your first host."
      >
        <template #actions>
          <button
            @click="showAddHostModal = true"
            class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
            </svg>
            Add First Host
          </button>
        </template>
      </EmptyState>

      <!-- Grid View -->
      <div v-else-if="viewMode === 'grid'" class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <HostCard
          v-for="host in hosts"
          :key="host.id"
          :host="host"
          @deploy="handleDeploy"
          @test="handleTestConnection"
          @edit="handleEditHost"
          @delete="handleDeleteHost"
        />
      </div>

      <!-- Table View -->
      <div v-else class="bg-white rounded-lg shadow overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Host
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                IP Address
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Group
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Deploy
              </th>
              <th scope="col" class="relative px-6 py-3">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="host in hosts" :key="host.id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="text-sm font-medium text-gray-900">{{ host.hostname }}</div>
                <div class="text-sm text-gray-500">{{ host.ssh_user }}</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ host.ip_address }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <ServiceStatusIndicator :status="host.status" :show-text="true" />
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ host.ansible_group || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ host.last_deployed_at ? formatDate(host.last_deployed_at) : 'Never' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <button
                  @click="handleDeploy(host.id)"
                  class="text-indigo-600 hover:text-indigo-900 mr-3"
                  :disabled="host.status === 'deploying'"
                >
                  Deploy
                </button>
                <button
                  @click="handleTestConnection(host.id)"
                  class="text-gray-600 hover:text-gray-900 mr-3"
                >
                  Test
                </button>
                <button
                  @click="handleDeleteHost(host.id)"
                  class="text-red-600 hover:text-red-900"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add Host Modal -->
    <AddHostModal
      :visible="showAddHostModal"
      @close="showAddHostModal = false"
      @submit="handleAddHost"
    />

    <!-- Deployment Progress Modal -->
    <DeploymentProgressModal
      :visible="showDeploymentModal"
      :deployment="currentDeployment"
      :allow-close="true"
      @close="showDeploymentModal = false"
      @refresh="handleRefreshDeployment"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useInfrastructure } from '@/composables/useInfrastructure'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for InfrastructureManager
const logger = createLogger('InfrastructureManager')
import HostCard from '@/components/infrastructure/HostCard.vue'
import AddHostModal from '@/components/infrastructure/AddHostModal.vue'
import DeploymentProgressModal from '@/components/infrastructure/DeploymentProgressModal.vue'
import ServiceStatusIndicator from '@/components/infrastructure/ServiceStatusIndicator.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { Host, Deployment } from '@/composables/useInfrastructure'
import { formatDate } from '@/utils/formatHelpers'

const {
  hosts,
  isLoading,
  activeHosts,
  pendingHosts,
  errorHosts,
  fetchHosts,
  addHost,
  deleteHost,
  deployHost,
  getDeploymentStatus,
  getDeploymentLogs,
  testHostConnection
} = useInfrastructure()

const viewMode = ref<'grid' | 'table'>('grid')
const showAddHostModal = ref(false)
const showDeploymentModal = ref(false)
const currentDeployment = ref<Deployment | null>(null)

onMounted(async () => {
  await refreshHosts()
})

async function refreshHosts() {
  await fetchHosts()
}

async function handleAddHost(formData: any) {
  try {
    await addHost(formData)
    showAddHostModal.value = false
    await refreshHosts()
  } catch (error) {
    logger.error('Failed to add host:', error)
  }
}

async function handleDeploy(hostId: string) {
  try {
    const deployment = await deployHost([hostId])
    currentDeployment.value = deployment as Deployment
    showDeploymentModal.value = true

    // Start polling for deployment status
    startDeploymentPolling(deployment.id)
  } catch (error) {
    logger.error('Failed to start deployment:', error)
  }
}

async function handleTestConnection(hostId: string) {
  await testHostConnection(hostId)
}

async function handleEditHost(host: Host) {
  // TODO: Implement edit modal
  logger.debug('Edit host:', host)
}

async function handleDeleteHost(hostId: string) {
  if (confirm('Are you sure you want to delete this host?')) {
    try {
      await deleteHost(hostId)
      await refreshHosts()
    } catch (error) {
      logger.error('Failed to delete host:', error)
    }
  }
}

async function handleRefreshDeployment() {
  if (currentDeployment.value) {
    const status = await getDeploymentStatus(currentDeployment.value.id)
    if (status) {
      currentDeployment.value = status as Deployment
    }

    const logs = await getDeploymentLogs(currentDeployment.value.id)
    if (logs && currentDeployment.value) {
      currentDeployment.value.logs = logs
    }
  }
}

let deploymentPollInterval: number | null = null

function startDeploymentPolling(deploymentId: string) {
  // Clear existing interval
  if (deploymentPollInterval) {
    clearInterval(deploymentPollInterval)
  }

  // Poll every 2 seconds
  deploymentPollInterval = setInterval(async () => {
    const status = await getDeploymentStatus(deploymentId)
    if (status) {
      currentDeployment.value = status as Deployment

      // Stop polling if deployment is complete
      if (status.status === 'success' || status.status === 'failed') {
        if (deploymentPollInterval) {
          clearInterval(deploymentPollInterval)
          deploymentPollInterval = null
        }
        await refreshHosts() // Refresh host list to update statuses
      }
    }

    // Also fetch logs
    const logs = await getDeploymentLogs(deploymentId)
    if (logs && currentDeployment.value) {
      currentDeployment.value.logs = logs
    }
  }, 2000) as unknown as number
}

</script>
