<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import OrgTreeNode from './OrgTreeNode.vue'
import type { OrgNode } from './OrgTreeNode.vue'

const logger = createLogger('OrgChart')
const api = useApiClient()

const tree = ref<OrgNode[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedNode = ref<OrgNode | null>(null)
const drawerOpen = ref(false)

async function fetchTree() {
  isLoading.value = true
  error.value = null
  try {
    const resp = await api.get<{ data: { nodes: OrgNode[] } }>('/api/llc/org-chart')
    tree.value = (resp as { data: { nodes: OrgNode[] } }).data?.nodes ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch org chart:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

async function toggleAgentPause(node: OrgNode) {
  const action = node.status === 'paused' ? 'resume' : 'pause'
  try {
    await api.post(`/api/llc/agents/${node.id}/${action}`, {})
    node.status = action === 'pause' ? 'paused' : 'idle'
    if (selectedNode.value?.id === node.id) selectedNode.value = { ...node }
  } catch (err: unknown) {
    logger.error('Toggle pause failed', err)
  }
}

function openDrawer(node: OrgNode) {
  selectedNode.value = node
  drawerOpen.value = true
}

function closeDrawer() {
  drawerOpen.value = false
  selectedNode.value = null
}

function formatTime(ts: string | null): string {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleString()
}

onMounted(fetchTree)
</script>

<template>
  <div class="p-4 max-w-7xl mx-auto">
    <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Org Chart</h1>

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchTree">Retry</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-gray-500">Loading…</div>

    <div v-else-if="tree.length === 0 && !error" class="text-center py-12 text-gray-400">No agents found.</div>

    <div v-else class="overflow-x-auto">
      <div class="min-w-max flex gap-6 items-start">
        <OrgTreeNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :depth="0"
          @select="openDrawer"
        />
      </div>
    </div>

    <!-- Agent Detail Drawer -->
    <transition name="slide">
      <div
        v-if="drawerOpen && selectedNode"
        class="fixed inset-y-0 right-0 w-80 bg-white dark:bg-gray-900 shadow-2xl border-l border-gray-200 dark:border-gray-700 z-50 flex flex-col"
      >
        <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Agent Detail</h2>
          <button class="text-gray-400 hover:text-gray-600" @click="closeDrawer">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div class="flex items-center gap-3">
            <div
              class="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold"
              :class="selectedNode.is_human ? 'bg-blue-100 text-blue-700' : 'bg-indigo-100 text-indigo-700'"
            >
              {{ selectedNode.name.charAt(0).toUpperCase() }}
            </div>
            <div>
              <p class="font-semibold text-gray-900 dark:text-gray-100">{{ selectedNode.name }}</p>
              <p class="text-sm text-gray-500">{{ selectedNode.title }}</p>
            </div>
          </div>

          <dl class="space-y-2 text-sm">
            <div class="flex justify-between">
              <dt class="text-gray-500">Adapter</dt>
              <dd class="text-gray-900 dark:text-gray-100 font-medium">{{ selectedNode.adapter_type }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Type</dt>
              <dd class="text-gray-900 dark:text-gray-100">{{ selectedNode.is_human ? 'Human' : 'AI Agent' }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Last Heartbeat</dt>
              <dd class="text-gray-900 dark:text-gray-100">{{ formatTime(selectedNode.last_heartbeat) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Budget</dt>
              <dd class="text-gray-900 dark:text-gray-100">
                {{ selectedNode.budget_spent }} / {{ selectedNode.budget_total }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Assigned Items</dt>
              <dd class="text-gray-900 dark:text-gray-100">{{ selectedNode.assigned_item_count }}</dd>
            </div>
          </dl>
        </div>
        <div class="px-5 py-4 border-t border-gray-200 dark:border-gray-700">
          <button
            class="w-full py-2 rounded-lg text-sm font-medium transition-colors"
            :class="selectedNode.status === 'paused'
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-amber-500 text-white hover:bg-amber-600'"
            @click="toggleAgentPause(selectedNode)"
          >
            {{ selectedNode.status === 'paused' ? 'Resume Agent' : 'Pause Agent' }}
          </button>
        </div>
      </div>
    </transition>
    <div v-if="drawerOpen" class="fixed inset-0 bg-black/20 z-40" @click="closeDrawer" />
  </div>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
