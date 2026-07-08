<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * FindingsPolicySettings - SLM operator panel for Company OS findings policy
 *
 * Reads/writes the SLM setting key `llc.findings_policy` (stored as a
 * JSON string: {enabled: bool, min_severity: str, require_approval_to_promote: bool,
 * run_on_index: bool, verify_batch_size: int}) via the SLM settings API.
 * Mirrors the DisposalPolicySettings.vue auth-store + fetch pattern.
 * Issue #11271 P3.
 */

import { onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const KEY = 'llc.findings_policy'
const authStore = useAuthStore()
const policy = reactive({
  enabled: false,
  min_severity: 'medium' as 'high' | 'medium' | 'low',
  require_approval_to_promote: false,
  run_on_index: false,
  verify_batch_size: 10,
})
const saving = ref(false)
const saved = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  error.value = null
  try {
    const res = await fetch(`${authStore.getApiUrl()}/api/settings/${KEY}`, {
      headers: authStore.getAuthHeaders(),
    })
    if (res.ok) {
      const setting = await res.json()
      const parsed = setting.value ? JSON.parse(setting.value) : {}
      policy.enabled = Boolean(parsed.enabled ?? false)
      policy.min_severity = (parsed.min_severity ?? 'medium') as 'high' | 'medium' | 'low'
      policy.require_approval_to_promote = Boolean(parsed.require_approval_to_promote ?? false)
      policy.run_on_index = Boolean(parsed.run_on_index ?? false)
      policy.verify_batch_size = Number(parsed.verify_batch_size ?? 10)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load findings policy'
  }
}

async function save(): Promise<void> {
  saving.value = true
  saved.value = false
  error.value = null
  const body = JSON.stringify({
    value: JSON.stringify({
      enabled: policy.enabled,
      min_severity: policy.min_severity,
      require_approval_to_promote: policy.require_approval_to_promote,
      run_on_index: policy.run_on_index,
      verify_batch_size: policy.verify_batch_size,
    }),
    description: 'Company OS findings policy',
  })
  const url = `${authStore.getApiUrl()}/api/settings/${KEY}`
  const headers = { ...authStore.getAuthHeaders(), 'Content-Type': 'application/json' }
  try {
    let res = await fetch(url, { method: 'PUT', headers, body })
    if (res.status === 404) {
      res = await fetch(url, { method: 'POST', headers, body })
    }
    saved.value = res.ok
    if (!res.ok) {
      error.value = 'Failed to save findings policy'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save findings policy'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-2">Findings Policy</h2>
      <p class="text-sm text-gray-500 mb-6">
        Controls how Company OS code-analysis findings are surfaced and promoted to work items.
      </p>

      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>
      <div v-if="saved" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
        Policy saved successfully.
      </div>

      <div class="space-y-6">
        <!-- Enabled -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Enable findings policy</label>
            <p class="text-xs text-gray-500 mt-1">
              When disabled, no findings are promoted to work items regardless of other settings.
            </p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="policy.enabled" class="sr-only peer" data-test="toggle-enabled" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>

        <!-- Minimum severity -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Minimum severity</label>
            <p class="text-xs text-gray-500 mt-1">
              Only findings at or above this severity level are promoted.
            </p>
          </div>
          <select
            v-model="policy.min_severity"
            class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            data-test="select-min-severity"
          >
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <!-- Require approval to promote -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Require approval to promote</label>
            <p class="text-xs text-gray-500 mt-1">
              When enabled, findings require operator approval before becoming work items.
            </p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="policy.require_approval_to_promote" class="sr-only peer" data-test="toggle-require-approval" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>

        <!-- Run on index -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">Run on index</label>
            <p class="text-xs text-gray-500 mt-1">
              Automatically trigger findings analysis whenever the code index is refreshed.
            </p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="policy.run_on_index" class="sr-only peer" data-test="toggle-run-on-index" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
        </div>

        <!-- Verify batch size -->
        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">Verify batch size</label>
            <p class="text-xs text-gray-500 mt-1">
              Number of findings processed per verification batch. Lower values reduce peak load.
            </p>
          </div>
          <input
            v-model.number="policy.verify_batch_size"
            type="number"
            min="1"
            class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            data-test="input-verify-batch-size"
          />
        </div>
      </div>

      <!-- Save Button -->
      <div class="mt-8 pt-6 border-t border-gray-200 flex justify-end">
        <button
          data-test="save-policy"
          :disabled="saving"
          class="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center gap-2 disabled:opacity-50"
          @click="save"
        >
          <svg v-if="saving" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ saving ? 'Saving…' : 'Save Policy' }}
        </button>
      </div>
    </div>
  </div>
</template>
