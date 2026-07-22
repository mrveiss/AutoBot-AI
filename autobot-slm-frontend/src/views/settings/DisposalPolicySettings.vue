<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * DisposalPolicySettings - SLM operator panel for project disposal policy
 *
 * Reads/writes the SLM setting key `llc.project_disposal_policy` (stored as a
 * JSON string: {retention_days: int, require_approval: bool}) via the SLM
 * settings API, using the shared `useSlmJsonSetting` fetch/save composable
 * (#11359). Issue #11129 P2.
 */

import { onMounted, reactive, ref } from 'vue'
import { useSlmJsonSetting } from '@/composables/useSlmJsonSetting'

interface DisposalPolicyPayload {
  retention_days: number
  require_approval: boolean
}

const KEY = 'llc.project_disposal_policy'
const { saving, saved, load: loadJson, save: saveJson } = useSlmJsonSetting<DisposalPolicyPayload>(KEY)
const policy = reactive({ retention_days: 0, require_approval: false })
const error = ref<string | null>(null)

async function load(): Promise<void> {
  error.value = null
  try {
    const parsed = await loadJson()
    if (parsed) {
      policy.retention_days = Number(parsed.retention_days ?? 0)
      policy.require_approval = Boolean(parsed.require_approval ?? false)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load disposal policy'
  }
}

async function save(): Promise<void> {
  error.value = null
  try {
    const ok = await saveJson(
      { retention_days: policy.retention_days, require_approval: policy.require_approval },
      'Company OS project disposal policy',
    )
    if (!ok) {
      error.value = 'Failed to save disposal policy'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save disposal policy'
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-2">{{ $t('settings.disposalPolicySettings.projectDisposalPolicy') }}</h2>
      <p class="text-sm text-gray-500 mb-6">{{ $t('settings.disposalPolicySettings.controlsHowCompanyOSProjectsAre') }}</p>

      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>
      <div v-if="saved" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">{{ $t('settings.disposalPolicySettings.policySavedSuccessfully') }}</div>

      <div class="space-y-6">
        <!-- Retention period -->
        <div class="flex items-center justify-between pb-4 border-b border-gray-100">
          <div>
            <label class="block text-sm font-medium text-gray-900">{{ $t('settings.disposalPolicySettings.retentionPeriodDays') }}</label>
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.disposalPolicySettings.howManyDaysAnArchivedProject') }}</p>
          </div>
          <input
            v-model.number="policy.retention_days"
            type="number"
            min="0"
            class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Require approval -->
        <div class="flex items-center justify-between">
          <div>
            <label class="block text-sm font-medium text-gray-900">{{ $t('settings.disposalPolicySettings.requireSecondPairOfEyesApproval') }}</label>
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.disposalPolicySettings.whenEnabledDisposalCreatesAnApproval') }}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="policy.require_approval" class="sr-only peer" />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
          </label>
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
          {{ saving ? $t('settings.disposalPolicySettings.saving') : $t('settings.disposalPolicySettings.savePolicy') }}
        </button>
      </div>
    </div>
  </div>
</template>
