<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import OrgTreeNode from './OrgTreeNode.vue'
import type { OrgNode } from './OrgTreeNode.vue'
import HireAgentModal from '@/components/llc/HireAgentModal.vue'

const logger = createLogger('OrgChart')
const api = useApiClient()
const { t } = useI18n()
const { companyId, resolveCompanyId } = useLlcCompanyContext()

const tree = ref<OrgNode[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedNode = ref<OrgNode | null>(null)
const drawerOpen = ref(false)
const showHire = ref(false) // GH#10219

async function fetchTree() {
  isLoading.value = true
  error.value = null
  try {
    const cid = await resolveCompanyId()
    if (!cid) {
      tree.value = []
      return
    }
    const resp = await api.get<{ nodes: OrgNode[] }>(`/api/llc/companies/${cid}/org-chart`)
    tree.value = resp?.nodes ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch org chart:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

async function toggleAgentPause(node: OrgNode) {
  if (!companyId.value) return
  const willPause = node.status !== 'paused'
  const cid = companyId.value
  try {
    // Explicit literal paths (not a template action) so each resolves to the
    // canonical /controls/agents/{id}/pause | /resume endpoint.
    if (willPause) {
      await api.post(`/api/llc/companies/${cid}/controls/agents/${node.id}/pause`, {})
    } else {
      await api.post(`/api/llc/companies/${cid}/controls/agents/${node.id}/resume`, {})
    }
    node.status = willPause ? 'paused' : 'idle'
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
  if (!ts) return t('llc.orgChart.never')
  return new Date(ts).toLocaleString()
}

onMounted(fetchTree)
</script>

<template>
  <div class="p-4 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-autobot-text-primary">{{ t('llc.orgChart.title') }}</h1>
      <button
        v-if="companyId"
        class="px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm hover:bg-indigo-700"
        @click="showHire = true"
      >
        {{ t('llc.orgChart.hireAgent') }}
      </button>
    </div>

    <HireAgentModal
      v-if="showHire && companyId"
      :company-id="companyId"
      @close="showHire = false"
      @hired="fetchTree"
    />

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchTree">{{ t('llc.orgChart.retry') }}</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-autobot-text-muted">{{ t('llc.orgChart.loading') }}</div>

    <div v-else-if="tree.length === 0 && !error" class="text-center py-12 text-autobot-text-muted">{{ t('llc.orgChart.empty') }}</div>

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
        class="fixed inset-y-0 right-0 w-80 bg-autobot-bg-card shadow-2xl border-l border-autobot-border z-50 flex flex-col"
      >
        <div class="flex items-center justify-between px-5 py-4 border-b border-autobot-border">
          <h2 class="text-lg font-semibold text-autobot-text-primary">{{ t('llc.orgChart.agentDetail') }}</h2>
          <button class="text-autobot-text-muted hover:text-autobot-text-secondary" @click="closeDrawer">
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
              <p class="font-semibold text-autobot-text-primary">{{ selectedNode.name }}</p>
              <p class="text-sm text-autobot-text-muted">{{ selectedNode.title }}</p>
            </div>
          </div>

          <dl class="space-y-2 text-sm">
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.adapter') }}</dt>
              <dd class="text-autobot-text-primary font-medium">{{ selectedNode.adapter_type }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.type') }}</dt>
              <dd class="text-autobot-text-primary">{{ selectedNode.is_human ? t('llc.orgChart.human') : t('llc.orgChart.aiAgent') }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.lastHeartbeat') }}</dt>
              <dd class="text-autobot-text-primary">{{ formatTime(selectedNode.last_heartbeat) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.budget') }}</dt>
              <dd class="text-autobot-text-primary">
                {{ selectedNode.budget_spent }} / {{ selectedNode.budget_total }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.assignedItems') }}</dt>
              <dd class="text-autobot-text-primary">{{ selectedNode.assigned_item_count }}</dd>
            </div>
          </dl>
        </div>
        <div class="px-5 py-4 border-t border-autobot-border">
          <button
            class="w-full py-2 rounded-lg text-sm font-medium transition-colors"
            :class="selectedNode.status === 'paused'
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-amber-500 text-white hover:bg-amber-600'"
            @click="toggleAgentPause(selectedNode)"
          >
            {{ selectedNode.status === 'paused' ? t('llc.orgChart.resumeAgent') : t('llc.orgChart.pauseAgent') }}
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
