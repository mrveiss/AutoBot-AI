<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, watch } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode } from '@/types/slm'

interface RoleInfo {
  name: string
  description: string
  category: string
  dependencies: string[]
}

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  deployed: [deploymentId: string]
}>()

const api = useSlmApi()
const fleetStore = useFleetStore()

const step = ref(1)
const selectedNodeId = ref<string>('')
const selectedRoles = ref<string[]>([])
const isDeploying = ref(false)
const deployError = ref<string | null>(null)
const roles = ref<RoleInfo[]>([])
const isLoadingRoles = ref(false)

// For manual IP input when no nodes exist
const manualMode = ref(false)
const manualHostname = ref('')
const manualIp = ref('')

const nodes = computed(() => fleetStore.nodeList)
const selectedNode = computed(() =>
  nodes.value.find((n: SLMNode) => n.node_id === selectedNodeId.value)
)

const canProceedStep1 = computed(() => {
  if (manualMode.value) {
    return manualHostname.value.trim() !== '' && manualIp.value.trim() !== ''
  }
  return selectedNodeId.value !== ''
})

const canProceedStep2 = computed(() => selectedRoles.value.length > 0)

// Group roles by category
const rolesByCategory = computed(() => {
  const groups: Record<string, RoleInfo[]> = {}
  for (const role of roles.value) {
    if (!groups[role.category]) {
      groups[role.category] = []
    }
    groups[role.category].push(role)
  }
  return groups
})

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      reset()
      loadData()
    }
  }
)

onMounted(() => {
  if (props.visible) {
    loadData()
  }
})

async function loadData(): Promise<void> {
  await Promise.all([fleetStore.fetchNodes(), fetchRoles()])

  // If no nodes exist, switch to manual mode
  if (nodes.value.length === 0) {
    manualMode.value = true
  }
}

async function fetchRoles(): Promise<void> {
  isLoadingRoles.value = true
  try {
    const response = await fetch('/api/deployments/roles', {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
      },
    })
    if (response.ok) {
      const data = await response.json()
      roles.value = data.roles
    }
  } catch (e) {
    // Use default roles from node-roles constants if API fails
    const { NODE_ROLE_METADATA } = await import('@/constants/node-roles')
    roles.value = Object.values(NODE_ROLE_METADATA).map((meta) => ({
      name: meta.name,
      description: meta.description,
      category: meta.category,
      dependencies: [],
    }))
  } finally {
    isLoadingRoles.value = false
  }
}

function reset(): void {
  step.value = 1
  selectedNodeId.value = ''
  selectedRoles.value = []
  deployError.value = null
  manualMode.value = false
  manualHostname.value = ''
  manualIp.value = ''
}

function toggleRole(roleName: string): void {
  const index = selectedRoles.value.indexOf(roleName)
  if (index === -1) {
    selectedRoles.value.push(roleName)
    // Auto-select dependencies
    const role = roles.value.find((r) => r.name === roleName)
    if (role?.dependencies) {
      for (const dep of role.dependencies) {
        if (!selectedRoles.value.includes(dep)) {
          selectedRoles.value.push(dep)
        }
      }
    }
  } else {
    selectedRoles.value.splice(index, 1)
  }
}

function isRoleSelected(roleName: string): boolean {
  return selectedRoles.value.includes(roleName)
}

function nextStep(): void {
  if (step.value < 3) {
    step.value++
  }
}

function prevStep(): void {
  if (step.value > 1) {
    step.value--
  }
}

async function deploy(): Promise<void> {
  isDeploying.value = true
  deployError.value = null

  try {
    let nodeId = selectedNodeId.value

    // If in manual mode, register the node first
    if (manualMode.value) {
      const newNode = await api.registerNode({
        hostname: manualHostname.value.trim(),
        ip_address: manualIp.value.trim(),
        roles: [],
      })
      nodeId = newNode.node_id
    }

    const deployment = await api.createDeployment({
      node_id: nodeId,
      roles: selectedRoles.value as any,
    })

    emit('deployed', deployment.deployment_id)
    emit('close')
  } catch (e) {
    deployError.value = e instanceof Error ? e.message : 'Failed to create deployment'
  } finally {
    isDeploying.value = false
  }
}

function getCategoryIcon(category: string): string {
  switch (category) {
    case 'core':
      return 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z'
    case 'data':
      return 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4'
    case 'application':
      return 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4'
    case 'ai':
      return 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'
    case 'automation':
      return 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'
    case 'observability':
      return 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'
    case 'infrastructure':
      return 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'
    default:
      return 'M13 10V3L4 14h7v7l9-11h-7z'
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
    @click.self="$emit('close')"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">New Deployment</h3>
          <p class="text-sm text-gray-500">Step {{ step }} of 3</p>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Progress Bar -->
      <div class="px-6 pt-4">
        <div class="flex items-center gap-2">
          <div
            v-for="s in 3"
            :key="s"
            :class="[
              'flex-1 h-2 rounded-full transition-colors',
              s <= step ? 'bg-primary-600' : 'bg-gray-200',
            ]"
          />
        </div>
        <div class="flex justify-between mt-2 text-xs text-gray-500">
          <span>Select Node</span>
          <span>Choose Roles</span>
          <span>Review & Deploy</span>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto px-6 py-4">
        <!-- Step 1: Select Node -->
        <div v-if="step === 1">
          <h4 class="text-base font-medium text-gray-900 mb-4">Select Target Node</h4>

          <!-- Manual mode toggle -->
          <div v-if="nodes.length > 0" class="mb-4">
            <label class="flex items-center gap-2 text-sm">
              <input
                v-model="manualMode"
                type="checkbox"
                class="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span class="text-gray-700">Enter IP address manually</span>
            </label>
          </div>

          <!-- Manual IP input -->
          <div v-if="manualMode" class="space-y-4">
            <div>
              <label class="label">Hostname</label>
              <input
                v-model="manualHostname"
                type="text"
                class="input"
                placeholder="e.g., web-server-01"
              />
            </div>
            <div>
              <label class="label">IP Address</label>
              <input
                v-model="manualIp"
                type="text"
                class="input"
                placeholder="e.g., 192.168.1.100"
              />
            </div>
            <p class="text-sm text-gray-500">
              The node will be registered automatically when you deploy.
            </p>
          </div>

          <!-- Node selection -->
          <div v-else class="space-y-2">
            <div v-if="nodes.length === 0" class="text-center py-8 text-gray-500">
              <p>No nodes registered yet.</p>
              <p class="text-sm mt-2">Switch to manual mode to enter an IP address.</p>
            </div>
            <div
              v-for="node in nodes"
              :key="node.node_id"
              @click="selectedNodeId = node.node_id"
              :class="[
                'p-4 border rounded-lg cursor-pointer transition-all',
                selectedNodeId === node.node_id
                  ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-200'
                  : 'border-gray-200 hover:border-gray-300',
              ]"
            >
              <div class="flex items-center justify-between">
                <div>
                  <div class="font-medium text-gray-900">{{ node.hostname }}</div>
                  <div class="text-sm text-gray-500">{{ node.ip_address }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <span
                    :class="[
                      'px-2 py-1 text-xs font-medium rounded-full',
                      node.status === 'healthy'
                        ? 'bg-green-100 text-green-800'
                        : node.status === 'offline'
                          ? 'bg-gray-100 text-gray-800'
                          : 'bg-yellow-100 text-yellow-800',
                    ]"
                  >
                    {{ node.status }}
                  </span>
                </div>
              </div>
              <div v-if="node.roles.length > 0" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="role in node.roles"
                  :key="role"
                  class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                >
                  {{ role }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 2: Select Roles -->
        <div v-else-if="step === 2">
          <h4 class="text-base font-medium text-gray-900 mb-4">Select Roles to Deploy</h4>

          <div v-if="isLoadingRoles" class="flex items-center justify-center py-8">
            <div class="animate-spin w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full" />
          </div>

          <div v-else class="space-y-6">
            <div v-for="(categoryRoles, category) in rolesByCategory" :key="category">
              <div class="flex items-center gap-2 mb-3">
                <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getCategoryIcon(category)" />
                </svg>
                <h5 class="text-sm font-medium text-gray-700 uppercase tracking-wide">{{ category }}</h5>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div
                  v-for="role in categoryRoles"
                  :key="role.name"
                  @click="toggleRole(role.name)"
                  :class="[
                    'p-3 border rounded-lg cursor-pointer transition-all',
                    isRoleSelected(role.name)
                      ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-200'
                      : 'border-gray-200 hover:border-gray-300',
                  ]"
                >
                  <div class="flex items-start gap-3">
                    <div
                      :class="[
                        'w-5 h-5 mt-0.5 rounded border-2 flex items-center justify-center transition-colors',
                        isRoleSelected(role.name)
                          ? 'border-primary-500 bg-primary-500'
                          : 'border-gray-300',
                      ]"
                    >
                      <svg
                        v-if="isRoleSelected(role.name)"
                        class="w-3 h-3 text-white"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fill-rule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clip-rule="evenodd"
                        />
                      </svg>
                    </div>
                    <div class="flex-1">
                      <div class="font-medium text-gray-900">{{ role.name }}</div>
                      <div class="text-sm text-gray-500">{{ role.description }}</div>
                      <div v-if="role.dependencies.length > 0" class="mt-1 text-xs text-gray-400">
                        Requires: {{ role.dependencies.join(', ') }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 3: Review -->
        <div v-else-if="step === 3">
          <h4 class="text-base font-medium text-gray-900 mb-4">Review Deployment</h4>

          <!-- Error Message -->
          <div
            v-if="deployError"
            class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
          >
            {{ deployError }}
          </div>

          <div class="space-y-4">
            <div class="p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500 mb-1">Target Node</div>
              <div v-if="manualMode" class="font-medium text-gray-900">
                {{ manualHostname }} ({{ manualIp }})
                <span class="text-xs text-gray-500 ml-2">(will be registered)</span>
              </div>
              <div v-else-if="selectedNode" class="font-medium text-gray-900">
                {{ selectedNode.hostname }} ({{ selectedNode.ip_address }})
              </div>
            </div>

            <div class="p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500 mb-2">Roles to Deploy</div>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="role in selectedRoles"
                  :key="role"
                  class="px-3 py-1 bg-primary-100 text-primary-700 rounded-full text-sm font-medium"
                >
                  {{ role }}
                </span>
              </div>
            </div>

            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div class="flex items-start gap-3">
                <svg class="w-5 h-5 text-blue-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="text-sm text-blue-700">
                  <p class="font-medium">What happens next?</p>
                  <ul class="mt-1 space-y-1 text-blue-600">
                    <li>1. Ansible playbook will be generated</li>
                    <li>2. SSH connection to target node established</li>
                    <li>3. Roles will be installed and configured</li>
                    <li>4. Services will be started and health-checked</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50">
        <button
          v-if="step > 1"
          @click="prevStep"
          class="btn btn-secondary"
          :disabled="isDeploying"
        >
          Back
        </button>
        <div v-else></div>

        <div class="flex gap-3">
          <button @click="$emit('close')" class="btn btn-secondary" :disabled="isDeploying">
            Cancel
          </button>
          <button
            v-if="step < 3"
            @click="nextStep"
            :disabled="(step === 1 && !canProceedStep1) || (step === 2 && !canProceedStep2)"
            class="btn btn-primary"
          >
            Next
          </button>
          <button
            v-else
            @click="deploy"
            :disabled="isDeploying"
            class="btn btn-primary flex items-center gap-2"
          >
            <svg
              v-if="isDeploying"
              class="animate-spin w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ isDeploying ? 'Deploying...' : 'Deploy' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
