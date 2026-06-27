// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

<script setup lang="ts">
/**
 * BudgetAuditView - Budget Policy Audit (#10488 Workstream A).
 *
 * Read-only operator oversight of every budget policy across the system
 * (agent / project / task / tenant scopes) and their hard-stop auto-pause
 * configuration. This is audit-only: creating, editing, and deleting budget
 * policies stays user-side in the user app. The SLM console issues NO
 * mutation calls.
 *
 * Reads the main AutoBot backend via the /autobot-api proxy
 * (-> /api/budget-policies). The body is flat
 * (response_model=BudgetPoliciesListResponse): { policies: [...], count: N }.
 */

import { ref, computed, onMounted } from 'vue'
import { useAutobotApi, type BudgetPolicy } from '@/composables/useAutobotApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BudgetAuditView')
const api = useAutobotApi()

const policies = ref<BudgetPolicy[]>([])
const loading = ref(false)
const error = ref('')

// Actions whose breach behaviour pauses the agent (hard-stop). Used to
// highlight policies that can halt a runaway agent.
const PAUSING_ACTIONS = ['pause', 'alert_then_pause']

const pausingCount = computed(
  () => policies.value.filter((p) => p.enabled && PAUSING_ACTIONS.includes(p.action)).length,
)

async function fetchPolicies(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getBudgetPolicies()
    policies.value = data.policies
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : 'Failed to fetch budget policies'
    logger.error('Error fetching budget policies:', err)
  } finally {
    loading.value = false
  }
}

function actionLabel(action: string): string {
  return action.replace(/_/g, ' ')
}

function actionClass(action: string): string {
  if (action === 'pause') {
    return 'bg-red-100 text-red-700'
  }
  if (action === 'alert_then_pause') {
    return 'bg-amber-100 text-amber-700'
  }
  return 'bg-blue-100 text-blue-700'
}

function isPausing(policy: BudgetPolicy): boolean {
  return policy.enabled && PAUSING_ACTIONS.includes(policy.action)
}

function formatThreshold(value: number): string {
  return `$${value.toFixed(2)}`
}

function formatWarning(value: number): string {
  return `${Math.round(value * 100)}%`
}

onMounted(() => {
  fetchPolicies()
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">
          {{ $t('budgetAudit.title') }}
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          {{ $t('budgetAudit.subtitle') }}
        </p>
      </div>
      <button
        class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        :disabled="loading"
        @click="fetchPolicies"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': loading }"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        {{ $t('budgetAudit.refresh') }}
      </button>
    </div>

    <!-- Read-only oversight notice -->
    <div
      class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-2"
    >
      <svg
        class="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <p class="text-sm text-blue-700">{{ $t('budgetAudit.readOnlyNotice') }}</p>
    </div>

    <!-- Error display -->
    <div
      v-if="error"
      class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg"
      role="alert"
    >
      <p class="text-sm font-semibold text-red-700">{{ error }}</p>
    </div>

    <!-- Summary -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs uppercase text-gray-500">{{ $t('budgetAudit.totalPolicies') }}</p>
        <p class="text-2xl font-bold text-gray-900">{{ policies.length }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <p class="text-xs uppercase text-gray-500">{{ $t('budgetAudit.autoPausePolicies') }}</p>
        <p class="text-2xl font-bold text-gray-900">{{ pausingCount }}</p>
      </div>
    </div>

    <!-- Policies table -->
    <div class="bg-white rounded-lg shadow overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 text-gray-500 uppercase text-xs">
          <tr>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.name') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.scope') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.scopeId') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.period') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.threshold') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.warning') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.action') }}</th>
            <th class="px-4 py-3 text-left">{{ $t('budgetAudit.status') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-if="loading && policies.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">
              {{ $t('budgetAudit.loading') }}
            </td>
          </tr>
          <tr v-else-if="policies.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">
              {{ $t('budgetAudit.noPolicies') }}
            </td>
          </tr>
          <tr v-for="policy in policies" :key="policy.id" class="hover:bg-gray-50">
            <td class="px-4 py-3 text-gray-900">
              {{ policy.name || $t('budgetAudit.unnamed') }}
            </td>
            <td class="px-4 py-3">
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
              >
                {{ policy.scope }}
              </span>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-gray-600">{{ policy.scope_id }}</td>
            <td class="px-4 py-3 text-gray-600">{{ policy.period }}</td>
            <td class="px-4 py-3 font-mono text-xs text-gray-900">
              {{ formatThreshold(policy.threshold_usd) }}
            </td>
            <td class="px-4 py-3 text-gray-600">{{ formatWarning(policy.warning_pct) }}</td>
            <td class="px-4 py-3">
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="actionClass(policy.action)"
              >
                {{ actionLabel(policy.action) }}
              </span>
            </td>
            <td class="px-4 py-3">
              <span
                v-if="!policy.enabled"
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500"
              >
                {{ $t('budgetAudit.disabled') }}
              </span>
              <span
                v-else-if="isPausing(policy)"
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700"
              >
                {{ $t('budgetAudit.canPause') }}
              </span>
              <span
                v-else
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700"
              >
                {{ $t('budgetAudit.active') }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
