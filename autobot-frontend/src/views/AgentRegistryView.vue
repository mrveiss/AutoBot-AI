<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AgentRegistryView — Agent Registry dashboard (#1794)
 *
 * Two-tab view: Backend Agents (AutoBot workers) and Specialized Agents
 * (parsed from .claude/agents/*.md files).
 */

import { ref, onMounted, computed } from 'vue'
import { useAgentRegistry, type SpecializedAgent, type BackendAgent } from '@/composables/useAgentRegistry'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentRegistryView')

const {
  backendAgents,
  specializedAgents,
  summary,
  selectedAgent,
  agentsByCategory,
  isLoading,
  isLoadingDetail,
  error,
  fetchAllAgents,
  fetchAgentDetail,
} = useAgentRegistry()

const activeTab = ref<'backend' | 'specialized'>('backend')
const showDetailModal = ref(false)
const categoryFilter = ref<string | null>(null)

const filteredSpecializedAgents = computed(() => {
  if (!categoryFilter.value) return specializedAgents.value
  return specializedAgents.value.filter(a => a.category === categoryFilter.value)
})

const categoryList = computed(() => {
  const cats = new Set(specializedAgents.value.map(a => a.category))
  return Array.from(cats).sort()
})

const colorMap: Record<string, string> = {
  cyan: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
  red: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  green: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  purple: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  gray: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
}

function getColorClasses(color: string): string {
  return colorMap[color] || colorMap.gray
}

const categoryIcons: Record<string, string> = {
  implementation: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
  analysis: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  planning: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01',
  specialized: 'M13 10V3L4 14h7v7l9-11h-7z',
  general: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
}

async function openAgentDetail(agent: SpecializedAgent) {
  showDetailModal.value = true
  await fetchAgentDetail(agent.id)
}

function closeDetailModal() {
  showDetailModal.value = false
  selectedAgent.value = null
}

onMounted(async () => {
  logger.debug('AgentRegistryView mounted')
  await fetchAllAgents()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-primary">Agent Registry</h2>
        <p class="text-sm text-secondary mt-1">
          Browse and monitor all registered agents
          <span v-if="summary" class="ml-2">
            &bull; {{ summary.total }} backend &bull; {{ summary.total_specialized }} specialized agents
          </span>
        </p>
      </div>
      <button
        @click="fetchAllAgents"
        :disabled="isLoading"
        class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', { 'animate-spin': isLoading }]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-autobot-error-bg border border-autobot-error rounded p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-autobot-error mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-autobot-error">Error</h3>
          <p class="text-sm text-autobot-error mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-default">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'backend'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'backend'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Backend Agents
          <span v-if="summary" class="ml-1 text-xs text-tertiary">({{ summary.total }})</span>
        </button>
        <button
          @click="activeTab = 'specialized'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'specialized'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Specialized Agents
          <span v-if="summary" class="ml-1 text-xs text-tertiary">({{ summary.total_specialized }})</span>
        </button>
      </nav>
    </div>

    <!-- Tab Content -->
    <div class="mt-6">
      <!-- Loading State -->
      <div v-if="isLoading && backendAgents.length === 0" class="flex items-center justify-center py-12">
        <div class="text-center">
          <div class="animate-spin rounded-sm h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p class="text-secondary mt-4">Loading agents...</p>
        </div>
      </div>

      <!-- Backend Agents Tab -->
      <div v-show="activeTab === 'backend' && !isLoading">
        <div v-if="backendAgents.length === 0" class="text-center py-12">
          <p class="text-secondary">No backend agents configured</p>
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="agent in backendAgents"
            :key="agent.id"
            class="bg-card border border-default rounded-lg p-4 hover:shadow-md transition-shadow"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-primary truncate">{{ agent.name }}</h3>
                <p class="text-xs text-secondary mt-1 line-clamp-2">{{ agent.description }}</p>
              </div>
              <span
                :class="[
                  'ml-2 flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium',
                  agent.status === 'connected'
                    ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                    : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                ]"
              >
                {{ agent.status }}
              </span>
            </div>
            <div class="mt-3 flex items-center gap-2 flex-wrap">
              <span class="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                {{ agent.model || 'no model' }}
              </span>
              <span class="text-xs text-tertiary">P{{ agent.priority }}</span>
              <span class="text-xs text-tertiary">{{ agent.config_source }}</span>
            </div>
            <div v-if="agent.tasks.length > 0" class="mt-2">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="task in agent.tasks.slice(0, 3)"
                  :key="task"
                  class="inline-block px-1.5 py-0.5 text-[10px] rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                >
                  {{ task }}
                </span>
                <span v-if="agent.tasks.length > 3" class="text-[10px] text-tertiary">
                  +{{ agent.tasks.length - 3 }} more
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Specialized Agents Tab -->
      <div v-show="activeTab === 'specialized' && !isLoading">
        <!-- Category Filter -->
        <div v-if="categoryList.length > 1" class="mb-4 flex flex-wrap gap-2">
          <button
            @click="categoryFilter = null"
            :class="[
              'px-3 py-1.5 text-xs font-medium rounded-sm border transition-colors',
              !categoryFilter
                ? 'bg-autobot-primary text-white border-autobot-primary'
                : 'bg-card text-secondary border-default hover:border-autobot-info'
            ]"
          >
            All ({{ specializedAgents.length }})
          </button>
          <button
            v-for="cat in categoryList"
            :key="cat"
            @click="categoryFilter = categoryFilter === cat ? null : cat"
            :class="[
              'px-3 py-1.5 text-xs font-medium rounded-sm border transition-colors capitalize',
              categoryFilter === cat
                ? 'bg-autobot-primary text-white border-autobot-primary'
                : 'bg-card text-secondary border-default hover:border-autobot-info'
            ]"
          >
            {{ cat }} ({{ agentsByCategory[cat]?.length || 0 }})
          </button>
        </div>

        <div v-if="filteredSpecializedAgents.length === 0" class="text-center py-12">
          <p class="text-secondary">No specialized agents found</p>
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="agent in filteredSpecializedAgents"
            :key="agent.id"
            class="bg-card border border-default rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
            @click="openAgentDetail(agent)"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-primary truncate">{{ agent.name }}</h3>
              </div>
              <div class="ml-2 flex items-center gap-1.5 flex-shrink-0">
                <span
                  v-if="agent.model"
                  :class="[
                    'inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium',
                    getColorClasses(agent.color)
                  ]"
                >
                  {{ agent.model }}
                </span>
                <span
                  :class="[
                    'inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium capitalize',
                    getColorClasses(agent.color)
                  ]"
                >
                  {{ agent.category }}
                </span>
              </div>
            </div>
            <p class="text-xs text-secondary mt-2 line-clamp-3">{{ agent.excerpt }}</p>
            <div v-if="agent.tools.length > 0" class="mt-2">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tool in agent.tools.slice(0, 4)"
                  :key="tool"
                  class="inline-block px-1.5 py-0.5 text-[10px] rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                >
                  {{ tool }}
                </span>
                <span v-if="agent.tools.length > 4" class="text-[10px] text-tertiary">
                  +{{ agent.tools.length - 4 }} more
                </span>
              </div>
            </div>
            <div class="mt-2 text-[10px] text-tertiary">
              {{ agent.source_file }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Agent Detail Modal -->
    <Teleport to="body">
      <div
        v-if="showDetailModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @click.self="closeDetailModal"
      >
        <div class="fixed inset-0 bg-black/50"></div>
        <div class="relative bg-card border border-default rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col">
          <!-- Modal Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-default">
            <div v-if="selectedAgent" class="flex items-center gap-3">
              <span
                :class="[
                  'inline-flex items-center px-2.5 py-1 rounded-sm text-xs font-medium',
                  getColorClasses(selectedAgent.color)
                ]"
              >
                {{ selectedAgent.model || 'default' }}
              </span>
              <h3 class="text-lg font-semibold text-primary">{{ selectedAgent.name }}</h3>
            </div>
            <div v-else class="h-6 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
            <button
              @click="closeDetailModal"
              class="text-secondary hover:text-primary"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <!-- Modal Body -->
          <div class="flex-1 overflow-y-auto px-6 py-4">
            <div v-if="isLoadingDetail" class="flex items-center justify-center py-12">
              <div class="animate-spin rounded-sm h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
            <div v-else-if="selectedAgent" class="space-y-4">
              <!-- Metadata -->
              <div class="flex flex-wrap gap-2">
                <span class="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 capitalize">
                  {{ selectedAgent.category }}
                </span>
                <span v-for="tool in selectedAgent.tools" :key="tool"
                  class="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                >
                  {{ tool }}
                </span>
              </div>
              <p class="text-xs text-tertiary">{{ selectedAgent.source_file }}</p>
              <!-- System Prompt -->
              <div class="mt-4">
                <h4 class="text-sm font-medium text-primary mb-2">System Prompt</h4>
                <pre class="text-xs text-secondary bg-gray-50 dark:bg-gray-800 rounded p-4 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">{{ selectedAgent.system_prompt }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
