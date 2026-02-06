<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Infrastructure Management View
 *
 * Issue #786: Main view for managing infrastructure setup playbooks.
 * Provides a dashboard for available playbooks and recent executions.
 */

import { ref, computed, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('InfrastructureView')
import InfrastructureWizard from '@/components/InfrastructureWizard.vue'

interface PlaybookInfo {
  id: string
  name: string
  description: string
  category: string
  playbook_file: string
  target_hosts: string[]
  variables: Record<string, unknown>
  estimated_duration: string
  requires_confirmation: boolean
}

interface PlaybookExecution {
  execution_id: string
  playbook_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  started_at: string | null
  completed_at: string | null
  output: string[]
  error: string | null
  triggered_by: string
}

const showWizard = ref(false)
const playbooks = ref<PlaybookInfo[]>([])
const recentExecutions = ref<PlaybookExecution[]>([])
const isLoading = ref(false)
const selectedExecution = ref<PlaybookExecution | null>(null)
const showOutputModal = ref(false)

const playbooksByCategory = computed(() => {
  const groups: Record<string, PlaybookInfo[]> = {}
  for (const playbook of playbooks.value) {
    if (!groups[playbook.category]) {
      groups[playbook.category] = []
    }
    groups[playbook.category].push(playbook)
  }
  return groups
})

onMounted(() => {
  loadPlaybooks()
})

async function loadPlaybooks(): Promise<void> {
  isLoading.value = true
  try {
    const response = await fetch('/api/infrastructure/playbooks', {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
      },
    })
    if (response.ok) {
      const data = await response.json()
      playbooks.value = data.playbooks
    }
  } catch (e) {
    logger.error('Error loading playbooks:', e)
  } finally {
    isLoading.value = false
  }
}

function handleExecuted(executionId: string): void {
  showWizard.value = false
  loadPlaybooks()
}

function getCategoryIcon(category: string): string {
  switch (category) {
    case 'database':
      return 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4'
    case 'monitoring':
      return 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'
    case 'security':
      return 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'
    case 'networking':
      return 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9'
    case 'storage':
      return 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4'
    default:
      return 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z'
  }
}

function getCategoryColor(category: string): string {
  switch (category) {
    case 'database':
      return 'bg-blue-100 text-blue-800'
    case 'monitoring':
      return 'bg-purple-100 text-purple-800'
    case 'security':
      return 'bg-green-100 text-green-800'
    case 'networking':
      return 'bg-cyan-100 text-cyan-800'
    case 'storage':
      return 'bg-orange-100 text-orange-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Infrastructure Setup</h1>
        <p class="text-gray-500 mt-1">
          Deploy and configure infrastructure components using Ansible playbooks
        </p>
      </div>
      <button @click="showWizard = true" class="btn btn-primary flex items-center gap-2">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        Run Setup Wizard
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full" />
    </div>

    <!-- Playbooks Grid -->
    <div v-else class="space-y-8">
      <div v-for="(categoryPlaybooks, category) in playbooksByCategory" :key="category">
        <!-- Category Header -->
        <div class="flex items-center gap-3 mb-4">
          <div :class="['p-2 rounded-lg', getCategoryColor(category)]">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getCategoryIcon(category)" />
            </svg>
          </div>
          <h2 class="text-lg font-semibold text-gray-900 capitalize">{{ category }}</h2>
        </div>

        <!-- Playbook Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="playbook in categoryPlaybooks"
            :key="playbook.id"
            class="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md transition-shadow"
          >
            <div class="flex items-start justify-between mb-3">
              <h3 class="font-semibold text-gray-900">{{ playbook.name }}</h3>
              <span
                :class="['px-2 py-1 text-xs font-medium rounded-full', getCategoryColor(category)]"
              >
                {{ category }}
              </span>
            </div>
            <p class="text-sm text-gray-600 mb-4 line-clamp-2">
              {{ playbook.description }}
            </p>
            <div class="flex items-center justify-between">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="host in playbook.target_hosts.slice(0, 2)"
                  :key="host"
                  class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                >
                  {{ host }}
                </span>
                <span
                  v-if="playbook.target_hosts.length > 2"
                  class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                >
                  +{{ playbook.target_hosts.length - 2 }}
                </span>
              </div>
              <span class="text-xs text-gray-500">
                ~{{ playbook.estimated_duration }}
              </span>
            </div>
            <button
              @click="showWizard = true"
              class="mt-4 w-full btn btn-secondary text-sm"
            >
              Configure & Run
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-if="!isLoading && playbooks.length === 0"
      class="text-center py-12 bg-white rounded-lg border border-gray-200"
    >
      <svg class="w-12 h-12 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">No playbooks available</h3>
      <p class="text-gray-500 mb-4">
        Infrastructure playbooks have not been configured yet.
      </p>
    </div>

    <!-- Info Panel -->
    <div class="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="text-sm text-blue-700">
          <p class="font-medium">About Infrastructure Setup</p>
          <p class="mt-1 text-blue-600">
            Infrastructure playbooks automate the deployment and configuration of system components.
            Each playbook is designed to set up specific services like databases, monitoring, or security tools.
            Run the Setup Wizard to execute a playbook with guided configuration.
          </p>
        </div>
      </div>
    </div>

    <!-- Infrastructure Wizard Modal -->
    <InfrastructureWizard
      :visible="showWizard"
      @close="showWizard = false"
      @executed="handleExecuted"
    />
  </div>
</template>
