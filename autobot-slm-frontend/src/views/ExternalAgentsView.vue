<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * External Agent Registry View (Issue #963)
 *
 * Manages external A2A-compliant agents: register, verify, edit, delete.
 */

import { onMounted, ref, computed } from 'vue'
import { useExternalAgents } from '@/composables/useExternalAgents'
import type { ExternalAgent, ExternalAgentCreate, ExternalAgentUpdate } from '@/types/slm'

const registry = useExternalAgents()

// ── modal state ────────────────────────────────────────────────────────────

const showModal = ref(false)
const modalMode = ref<'create' | 'edit'>('create')
const editTarget = ref<ExternalAgent | null>(null)
const isSaving = ref(false)
const saveError = ref<string | null>(null)

const form = ref({
  name: '',
  base_url: '',
  description: '',
  tags: '',
  enabled: true,
  ssl_verify: true,
  api_key: '',
})

function openCreate() {
  modalMode.value = 'create'
  editTarget.value = null
  form.value = { name: '', base_url: '', description: '', tags: '', enabled: true, ssl_verify: true, api_key: '' }
  saveError.value = null
  showModal.value = true
}

function openEdit(agent: ExternalAgent) {
  modalMode.value = 'edit'
  editTarget.value = agent
  form.value = {
    name: agent.name,
    base_url: agent.base_url,
    description: agent.description || '',
    tags: (agent.tags || []).join(', '),
    enabled: agent.enabled,
    ssl_verify: true,
    api_key: '',
  }
  saveError.value = null
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

// ── detail panel ───────────────────────────────────────────────────────────

const detailAgent = ref<ExternalAgent | null>(null)
const showDetail = ref(false)
const isLoadingDetail = ref(false)

async function openDetail(agent: ExternalAgent) {
  isLoadingDetail.value = true
  showDetail.value = true
  const full = await registry.getAgent(agent.id)
  if (full) detailAgent.value = full
  isLoadingDetail.value = false
}

function closeDetail() {
  showDetail.value = false
  detailAgent.value = null
}

// ── CRUD actions ───────────────────────────────────────────────────────────

async function saveAgent() {
  isSaving.value = true
  saveError.value = null

  const tags = form.value.tags
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

  if (modalMode.value === 'create') {
    const payload: ExternalAgentCreate = {
      name: form.value.name,
      base_url: form.value.base_url,
      description: form.value.description || undefined,
      tags,
      enabled: form.value.enabled,
      ssl_verify: form.value.ssl_verify,
      api_key: form.value.api_key || undefined,
    }
    const result = await registry.createAgent(payload)
    if (result) {
      await registry.fetchAgents()
      showModal.value = false
    } else {
      saveError.value = registry.error || 'Failed to register agent'
    }
  } else if (editTarget.value) {
    const payload: ExternalAgentUpdate = {
      name: form.value.name,
      description: form.value.description || undefined,
      tags,
      enabled: form.value.enabled,
      ssl_verify: form.value.ssl_verify,
    }
    if (form.value.api_key !== '') {
      payload.api_key = form.value.api_key
    }
    const result = await registry.updateAgent(editTarget.value.id, payload)
    if (result) {
      await registry.fetchAgents()
      showModal.value = false
    } else {
      saveError.value = registry.error || 'Failed to update agent'
    }
  }

  isSaving.value = false
}

async function deleteAgent(agent: ExternalAgent) {
  if (!confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
  await registry.deleteAgent(agent.id)
}

// ── verify / refresh ───────────────────────────────────────────────────────

const verifyingId = ref<number | null>(null)
const refreshingId = ref<number | null>(null)

async function verifyAgent(agent: ExternalAgent) {
  verifyingId.value = agent.id
  await registry.verifyAgent(agent.id)
  await registry.fetchAgents()
  verifyingId.value = null
}

async function refreshCard(agent: ExternalAgent) {
  refreshingId.value = agent.id
  await registry.refreshAgentCard(agent.id)
  refreshingId.value = null
}

// ── helpers ────────────────────────────────────────────────────────────────

function skillCountLabel(agent: ExternalAgent): string {
  if (!agent.verified) return '—'
  return `${agent.skill_count} skill${agent.skill_count !== 1 ? 's' : ''}`
}

function statusClass(agent: ExternalAgent): string {
  if (!agent.enabled) return 'text-gray-400'
  if (agent.verified) return 'text-success-500'
  if (agent.card_error) return 'text-danger-500'
  return 'text-warning-500'
}

function statusLabel(agent: ExternalAgent): string {
  if (!agent.enabled) return 'Disabled'
  if (agent.verified) return 'Verified'
  if (agent.card_error) return 'Error'
  return 'Unverified'
}

const detailCardJson = computed(() => {
  if (!detailAgent.value?.card_data) return null
  return JSON.stringify(detailAgent.value.card_data, null, 2)
})

// ── lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  registry.fetchAgents()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-100">External Agent Registry</h1>
        <p class="text-sm text-gray-400 mt-1">
          Manage external A2A-compliant agents that AutoBot can route tasks to.
        </p>
      </div>
      <button
        class="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors"
        @click="openCreate"
      >
        + Register Agent
      </button>
    </div>

    <!-- Error banner -->
    <div
      v-if="registry.error"
      class="p-3 bg-danger-900/30 border border-danger-700 rounded-lg text-danger-300 text-sm"
    >
      {{ registry.error }}
    </div>

    <!-- Loading -->
    <div v-if="registry.isLoading" class="flex justify-center py-12 text-gray-400 text-sm">
      Loading agents…
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!registry.isLoading && registry.agents.length === 0"
      class="text-center py-12 text-gray-500 text-sm"
    >
      No external agents registered yet.
    </div>

    <!-- Agent table -->
    <div v-else class="bg-gray-800 rounded-xl overflow-hidden border border-gray-700">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-700 text-gray-400 text-left">
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">URL</th>
            <th class="px-4 py-3 font-medium">Status</th>
            <th class="px-4 py-3 font-medium">Skills</th>
            <th class="px-4 py-3 font-medium">Tags</th>
            <th class="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="agent in registry.agents"
            :key="agent.id"
            class="border-b border-gray-700/50 hover:bg-gray-750 transition-colors"
          >
            <td class="px-4 py-3">
              <button
                class="font-medium text-gray-100 hover:text-primary-400 transition-colors text-left"
                @click="openDetail(agent)"
              >
                {{ agent.name }}
              </button>
              <div v-if="agent.description" class="text-xs text-gray-500 mt-0.5 line-clamp-1">
                {{ agent.description }}
              </div>
            </td>
            <td class="px-4 py-3 text-gray-400 font-mono text-xs truncate max-w-xs">
              {{ agent.base_url }}
            </td>
            <td class="px-4 py-3">
              <span :class="['font-medium', statusClass(agent)]">
                {{ statusLabel(agent) }}
              </span>
              <div v-if="agent.card_error" class="text-xs text-danger-400 mt-0.5">
                {{ agent.card_error }}
              </div>
            </td>
            <td class="px-4 py-3 text-gray-300">{{ skillCountLabel(agent) }}</td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in agent.tags"
                  :key="tag"
                  class="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-xs"
                >
                  {{ tag }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <button
                  class="text-xs text-primary-400 hover:text-primary-300 disabled:opacity-50"
                  :disabled="verifyingId === agent.id"
                  @click="verifyAgent(agent)"
                >
                  {{ verifyingId === agent.id ? 'Verifying…' : 'Verify' }}
                </button>
                <button
                  class="text-xs text-gray-400 hover:text-gray-300 disabled:opacity-50"
                  :disabled="refreshingId === agent.id"
                  @click="refreshCard(agent)"
                >
                  {{ refreshingId === agent.id ? 'Queued' : 'Refresh' }}
                </button>
                <button
                  class="text-xs text-gray-400 hover:text-gray-200"
                  @click="openEdit(agent)"
                >
                  Edit
                </button>
                <button
                  class="text-xs text-danger-400 hover:text-danger-300"
                  @click="deleteAgent(agent)"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Register / Edit Modal -->
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      @click.self="closeModal"
    >
      <div class="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-lg p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-100">
          {{ modalMode === 'create' ? 'Register External Agent' : 'Edit Agent' }}
        </h2>

        <div class="space-y-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">Name *</label>
            <input
              v-model="form.name"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-primary-500"
              placeholder="My External Agent"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Base URL *</label>
            <input
              v-model="form.base_url"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-primary-500 font-mono"
              placeholder="https://agent.example.com"
              :disabled="modalMode === 'edit'"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Description</label>
            <input
              v-model="form.description"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-primary-500"
              placeholder="Optional description"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Tags (comma-separated)</label>
            <input
              v-model="form.tags"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-primary-500"
              placeholder="finance, analysis"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">
              Bearer Token (API Key)
              <span v-if="modalMode === 'edit'" class="text-gray-500">— leave blank to keep existing</span>
            </label>
            <input
              v-model="form.api_key"
              type="password"
              class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-primary-500 font-mono"
              placeholder="sk-..."
            />
          </div>
          <div class="flex items-center gap-6">
            <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input v-model="form.enabled" type="checkbox" class="accent-primary-500" />
              Enabled
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input v-model="form.ssl_verify" type="checkbox" class="accent-primary-500" />
              Verify SSL
            </label>
          </div>
        </div>

        <div
          v-if="saveError"
          class="p-2 bg-danger-900/30 border border-danger-700 rounded text-danger-300 text-xs"
        >
          {{ saveError }}
        </div>

        <div class="flex justify-end gap-3 pt-2">
          <button
            class="px-4 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors"
            @click="closeModal"
          >
            Cancel
          </button>
          <button
            class="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            :disabled="isSaving || !form.name || !form.base_url"
            @click="saveAgent"
          >
            {{ isSaving ? 'Saving…' : modalMode === 'create' ? 'Register' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Detail Panel -->
    <div
      v-if="showDetail"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      @click.self="closeDetail"
    >
      <div class="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-2xl p-6 space-y-4 max-h-[80vh] overflow-y-auto">
        <div v-if="isLoadingDetail" class="text-gray-400 text-sm text-center py-8">
          Loading…
        </div>
        <template v-else-if="detailAgent">
          <div class="flex items-start justify-between">
            <div>
              <h2 class="text-lg font-semibold text-gray-100">{{ detailAgent.name }}</h2>
              <p class="text-xs text-gray-400 font-mono mt-0.5">{{ detailAgent.base_url }}</p>
            </div>
            <span :class="['text-sm font-medium', statusClass(detailAgent)]">
              {{ statusLabel(detailAgent) }}
            </span>
          </div>

          <div v-if="detailAgent.description" class="text-sm text-gray-300">
            {{ detailAgent.description }}
          </div>

          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div class="text-xs text-gray-500 mb-0.5">Skills</div>
              <div class="text-gray-200">{{ skillCountLabel(detailAgent) }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500 mb-0.5">Card Fetched</div>
              <div class="text-gray-200">
                {{ detailAgent.card_fetched_at
                  ? new Date(detailAgent.card_fetched_at).toLocaleString()
                  : 'Never' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-gray-500 mb-0.5">Created By</div>
              <div class="text-gray-200">{{ detailAgent.created_by || '—' }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500 mb-0.5">Tags</div>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in detailAgent.tags"
                  :key="tag"
                  class="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-xs"
                >
                  {{ tag }}
                </span>
                <span v-if="!detailAgent.tags.length" class="text-gray-500">None</span>
              </div>
            </div>
          </div>

          <div v-if="detailAgent.card_error" class="p-2 bg-danger-900/30 border border-danger-700 rounded text-danger-300 text-xs">
            Card error: {{ detailAgent.card_error }}
          </div>

          <div v-if="detailCardJson">
            <div class="text-xs text-gray-500 mb-1">Agent Card (JSON)</div>
            <pre class="bg-gray-900 rounded-lg p-3 text-xs text-gray-300 overflow-x-auto max-h-64">{{ detailCardJson }}</pre>
          </div>
        </template>

        <div class="flex justify-end pt-2">
          <button
            class="px-4 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors"
            @click="closeDetail"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
