<script setup lang="ts">
import { BaseAlert, BaseSwitch } from '@autobot/ui'
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NotificationsSettings - Notification preferences
 *
 * Configure alert and notification settings.
 */

import { ref, onMounted } from 'vue'
import { listSettings, upsertSetting } from '@/utils/slmSettingsApi'

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const notifications = ref({
  node_health_alerts: true,
  deployment_notifications: true,
  backup_completion_alerts: true,
  maintenance_reminders: false,
  security_alerts: true,
  performance_warnings: true,
  email_notifications: false,
  email_address: '',
})

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    // #13140: canonical SLM client. A rejected session now surfaces as an
    // error (and clears the session) instead of being swallowed and leaving
    // the panel showing its hard-coded defaults.
    const data = await listSettings()
    data.forEach((s) => {
      if (s.value !== null && s.value !== undefined && s.key in notifications.value) {
        const key = s.key as keyof typeof notifications.value
        if (typeof notifications.value[key] === 'boolean') {
          (notifications.value as unknown as Record<string, boolean>)[key] = s.value === 'true'
        } else {
          (notifications.value as Record<string, string | number | boolean>)[key] = s.value
        }
      }
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function saveSettings(): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
    // #13140: the previous copy discarded every response, so a rejected write
    // still reported "Notification settings saved successfully".
    const failed: string[] = []
    for (const [key, value] of Object.entries(notifications.value)) {
      if (!(await upsertSetting(key, { value: String(value) }))) {
        failed.push(key)
      }
    }
    if (failed.length > 0) {
      throw new Error(`Failed to save setting(s): ${failed.join(', ')}`)
    }
    success.value = 'Notification settings saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save settings'
  } finally {
    saving.value = false
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="p-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Messages -->
      <BaseAlert v-if="error" variant="error" class="mb-4" :message="error" />
      <div v-if="success" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
        {{ success }}
      </div>

      <!-- Alert Types -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6 mb-6">
        <h2 class="text-lg font-semibold mb-6">{{ $t('settings.notificationsSettings.alertTypes') }}</h2>
        <p class="text-sm text-gray-500 mb-6">
          {{ $t('settings.notificationsSettings.chooseWhichTypesOf') }}
        </p>

        <div class="space-y-4">
          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.nodeHealthAlerts') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.getNotifiedWhenNodes') }}</p>
            </div>
            <BaseSwitch v-model="notifications.node_health_alerts" :label="$t('settings.notificationsSettings.nodeHealthAlerts')" />
          </div>

          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.deploymentNotifications') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.notificationsForDeploymentProgress') }}</p>
            </div>
            <BaseSwitch v-model="notifications.deployment_notifications" :label="$t('settings.notificationsSettings.deploymentNotifications')" />
          </div>

          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.backupCompletionAlerts') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.getNotifiedWhenBackups') }}</p>
            </div>
            <BaseSwitch v-model="notifications.backup_completion_alerts" :label="$t('settings.notificationsSettings.backupCompletionAlerts')" />
          </div>

          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.maintenanceReminders') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.remindersForScheduledMaintenance') }}</p>
            </div>
            <BaseSwitch v-model="notifications.maintenance_reminders" :label="$t('settings.notificationsSettings.maintenanceReminders')" />
          </div>

          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.securityAlerts') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.criticalSecurityNotifications') }}</p>
            </div>
            <BaseSwitch v-model="notifications.security_alerts" :label="$t('settings.notificationsSettings.securityAlerts')" />
          </div>

          <div class="flex items-center justify-between py-3">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.performanceWarnings') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.alertsForPerformanceDegradation') }}</p>
            </div>
            <BaseSwitch v-model="notifications.performance_warnings" :label="$t('settings.notificationsSettings.performanceWarnings')" />
          </div>
        </div>
      </div>

      <!-- Email Notifications -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
        <h2 class="text-lg font-semibold mb-6">{{ $t('settings.notificationsSettings.emailNotifications') }}</h2>

        <div class="space-y-4">
          <div class="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p class="font-medium text-gray-900">{{ $t('settings.notificationsSettings.enableEmail') }}</p>
              <p class="text-sm text-gray-500">{{ $t('settings.notificationsSettings.sendNotificationsViaEmail') }}</p>
            </div>
            <BaseSwitch v-model="notifications.email_notifications" :label="$t('settings.notificationsSettings.enableEmail')" />
          </div>

          <div v-if="notifications.email_notifications" class="py-3">
            <label class="block text-sm font-medium text-gray-900 mb-2">{{ $t('settings.notificationsSettings.emailAddress') }}</label>
            <input
              v-model="notifications.email_address"
              type="email"
              :placeholder="$t('settings.notificationsSettings.adminExampleCom')"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        <!-- Save Button -->
        <div class="mt-6 pt-6 border-t border-gray-200 flex justify-end">
          <button
            @click="saveSettings"
            :disabled="saving"
            class="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ saving ? $t('settings.notificationsSettings.saving') : $t('settings.notificationsSettings.saveChanges') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
