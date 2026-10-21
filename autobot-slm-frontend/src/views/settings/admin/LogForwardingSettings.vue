// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * LogForwardingSettings - Log Forwarding Management
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides management of log forwarding to external systems like Syslog, Elasticsearch, Loki.
 */

import { ref, reactive, onMounted } from 'vue'
import { BaseAlert, BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import { useAutobotApi } from '@/composables/useAutobotApi'
import type { LogForwardingDestination } from '@/composables/autobotAdminModels'
import {
  defaultForm, formFromDestination, destinationTypes, getUrlPlaceholder, buildCreateBody, buildUpdateBody,
} from './logForwardingForm'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LogForwardingSettings')
const { t } = useI18n()

const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const toggling = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Service status (GET /status carries no auto_start; see autoStart below)
const status = reactive({
  running: false,
  total_destinations: 0,
  enabled_destinations: 0,
  healthy_destinations: 0,
  total_sent: 0,
  total_failed: 0,
})
const autoStart = ref(false)
// A failed read is not "off": the toggle stays disabled until a read succeeds (#18797 review).
const autoStartLoaded = ref(false)
const autoStartSaving = ref(false)

// Destinations, keyed by name
const destinations = ref<LogForwardingDestination[]>([])

// Modal state
const showModal = ref(false)
const editingDestination = ref<LogForwardingDestination | null>(null)
const deleteTarget = ref<string | null>(null)

const formData = reactive(defaultForm())

// A failed status fetch must not read as "stopped": the defaults in `status`
// would then offer Start for a service that may be running (#17971 review).
const statusLoaded = ref(false)

async function fetchStatus(): Promise<void> {
  try {
    const statusData = await api.getLogForwardingStatus()
    if (statusData) {
      Object.assign(status, statusData)
    }
    statusLoaded.value = true
  } catch (e) {
    // Status endpoint may not be available
    statusLoaded.value = false
    logger.debug('Log forwarding status unavailable:', e)
  }
}

async function fetchAutoStart(): Promise<void> {
  try {
    const data = await api.getLogForwardingAutoStart()
    autoStart.value = !!data?.auto_start
    autoStartLoaded.value = true
  } catch (e) {
    autoStartLoaded.value = false
    logger.debug('Log forwarding auto-start unavailable:', e)
  }
}

async function fetchDestinations(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    destinations.value = await api.getLogForwardingDestinations()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.loadFailed')
  } finally {
    loading.value = false
  }
}

async function toggleService(): Promise<void> {
  if (!statusLoaded.value) return
  toggling.value = true
  error.value = null

  try {
    if (status.running) {
      await api.stopLogForwarding()
    } else {
      await api.startLogForwarding()
    }
    await fetchStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.toggleFailed')
  } finally {
    toggling.value = false
  }
}

async function toggleAutoStart(event: Event): Promise<void> {
  // The native checkbox has already flipped; it shows the confirmed value until the server answers.
  const box = event.target as HTMLInputElement
  box.checked = autoStart.value
  if (!autoStartLoaded.value || autoStartSaving.value) return
  autoStartSaving.value = true
  try {
    const result = await api.setLogForwardingAutoStart(!autoStart.value)
    autoStart.value = result.auto_start
    success.value = t(autoStart.value ? 'settings.admin.logForwardingSettings.autoStartEnabled' : 'settings.admin.logForwardingSettings.autoStartDisabled')
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.autoStartFailed')
  } finally {
    autoStartSaving.value = false
    box.checked = autoStart.value
  }
}

function openAddModal(): void {
  editingDestination.value = null
  resetForm()
  showModal.value = true
}

function openEditModal(dest: LogForwardingDestination): void {
  editingDestination.value = dest
  Object.assign(formData, formFromDestination(dest))
  showModal.value = true
}

function resetForm(): void {
  Object.assign(formData, defaultForm())
}

function closeModal(): void {
  showModal.value = false
  editingDestination.value = null
  resetForm()
}

async function saveDestination(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    if (editingDestination.value) {
      await api.updateLogForwardingDestination(editingDestination.value.name, buildUpdateBody(formData))
    } else {
      await api.createLogForwardingDestination(buildCreateBody(formData))
    }

    success.value = t(editingDestination.value ? 'settings.admin.logForwardingSettings.destinationUpdated' : 'settings.admin.logForwardingSettings.destinationCreated')
    closeModal()
    await fetchDestinations()
    await fetchStatus()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.saveFailed')
  } finally {
    saving.value = false
  }
}

async function testDestination(name: string): Promise<void> {
  testing.value = true
  error.value = null

  try {
    const result = await api.testLogForwardingDestination(name)
    if (result.healthy) {
      success.value = t('settings.admin.logForwardingSettings.testSucceeded')
    } else {
      error.value = result.message
    }
    await fetchDestinations()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.testFailed')
  } finally {
    testing.value = false
  }
}

async function testAllDestinations(): Promise<void> {
  testing.value = true
  error.value = null

  try {
    const response = await api.testAllLogForwardingDestinations()
    success.value = t('settings.admin.logForwardingSettings.testAllSummary', { healthy: response.healthy, total: response.total })
    await fetchDestinations()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.testAllFailed')
  } finally {
    testing.value = false
  }
}

function confirmDelete(name: string): void {
  deleteTarget.value = name
}

async function deleteDestination(): Promise<void> {
  if (!deleteTarget.value) return

  saving.value = true
  error.value = null

  try {
    await api.deleteLogForwardingDestination(deleteTarget.value)
    success.value = t('settings.admin.logForwardingSettings.destinationDeleted')
    deleteTarget.value = null
    await fetchDestinations()
    await fetchStatus()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.admin.logForwardingSettings.deleteFailed')
  } finally {
    saving.value = false
  }
}

// Initialize
onMounted(async () => {
  await Promise.all([fetchStatus(), fetchAutoStart(), fetchDestinations()])
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <BaseAlert v-if="error" variant="error" :message="error" dismissible :dismiss-label="$t('settings.admin.logForwardingSettings.dismissError')" @dismiss="error = null" />

    <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3">
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Service Status -->
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-4">
          <div
            :class="[
              'w-4 h-4 rounded-full',
              !statusLoaded ? 'bg-gray-400' : status.running ? 'bg-green-500 animate-pulse' : 'bg-red-500',
            ]"
          ></div>
          <div>
            <h2 class="text-lg font-semibold text-gray-900">
              {{ $t('settings.admin.logForwardingSettings.logForwardingService') }}
            </h2>
            <p class="text-sm text-gray-500">
              {{ !statusLoaded ? $t('settings.admin.logForwardingSettings.statusUnknown') : status.running ? $t('settings.admin.logForwardingSettings.serviceRunning') : $t('settings.admin.logForwardingSettings.serviceStopped') }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <button
            @click="toggleService"
            :disabled="toggling || !statusLoaded"
            :class="[
              'px-4 py-2 rounded-lg flex items-center gap-2 font-medium',
              status.running
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-green-500 text-white hover:bg-green-600',
              'disabled:opacity-50',
            ]"
          >
            <svg v-if="toggling" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path v-if="status.running" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              <path v-if="status.running" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            </svg>
            {{ status.running ? $t('settings.admin.logForwardingSettings.stop') : $t('settings.admin.logForwardingSettings.start') }}
          </button>

          <button
            @click="testAllDestinations"
            :disabled="testing"
            class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="testing" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ $t('settings.admin.logForwardingSettings.testAll') }}
          </button>

          <button
            @click="fetchStatus(); fetchDestinations()"
            class="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="p-4 bg-gray-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-gray-900">{{ status.total_destinations }}</p>
          <p class="text-sm text-gray-500">{{ $t('settings.admin.logForwardingSettings.total') }}</p>
        </div>
        <div class="p-4 bg-green-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-green-600">{{ status.healthy_destinations }}</p>
          <p class="text-sm text-gray-500">{{ $t('settings.admin.logForwardingSettings.healthy') }}</p>
        </div>
        <div class="p-4 bg-blue-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-blue-600">{{ status.total_sent }}</p>
          <p class="text-sm text-gray-500">{{ $t('settings.admin.logForwardingSettings.sent') }}</p>
        </div>
        <div class="p-4 bg-red-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-red-600">{{ status.total_failed }}</p>
          <p class="text-sm text-gray-500">{{ $t('settings.admin.logForwardingSettings.failed') }}</p>
        </div>
      </div>

      <!-- Auto-start toggle -->
      <div class="flex items-center gap-3 pt-4 border-t border-gray-200">
        <label class="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            :checked="autoStart"
            :disabled="!autoStartLoaded || autoStartSaving"
            data-test="auto-start"
            @change="toggleAutoStart"
            class="sr-only peer"
          />
          <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
        </label>
        <span class="text-sm text-gray-700">{{ $t('settings.admin.logForwardingSettings.autoStartOnBackend') }}</span>
      </div>
    </div>

    <!-- Destinations -->
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
      <div class="p-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h3 class="font-semibold text-gray-900">{{ $t('settings.admin.logForwardingSettings.destinations') }}</h3>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ $t('settings.admin.logForwardingSettings.addDestination') }}
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Empty State -->
      <div v-else-if="destinations.length === 0" class="p-8 text-center">
        <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-gray-500 mb-4">{{ $t('settings.admin.logForwardingSettings.noLogForwardingDestinations') }}</p>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          {{ $t('settings.admin.logForwardingSettings.addYourFirstDestination') }}
        </button>
      </div>

      <!-- Destinations List -->
      <div v-else class="divide-y divide-gray-100">
        <div
          v-for="dest in destinations"
          :key="dest.name"
          :class="[
            'p-4 hover:bg-gray-50 transition-colors',
            !dest.enabled && 'opacity-60',
          ]"
        >
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-3">
              <span
                :class="[
                  'px-2 py-1 rounded-sm text-xs font-semibold uppercase',
                  dest.type === 'syslog' ? 'bg-teal-100 text-teal-700' : '',
                  dest.type === 'webhook' ? 'bg-pink-100 text-pink-700' : '',
                  dest.type === 'file' ? 'bg-gray-100 text-gray-700' : '',
                  dest.type === 'elasticsearch' ? 'bg-amber-100 text-amber-700' : '',
                ]"
              >
                {{ dest.type }}
              </span>
              <div>
                <h4 class="font-medium text-gray-900">{{ dest.name }}</h4>
                <p class="text-sm text-gray-500">
                  {{ dest.url || dest.file_path || $t('settings.admin.logForwardingSettings.noEndpointConfigured') }}
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <button
                @click="testDestination(dest.name)"
                class="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-sm"
                :title="$t('settings.admin.logForwardingSettings.testConnection')"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </button>
              <button
                @click="openEditModal(dest)"
                class="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded-sm"
                :title="$t('settings.admin.logForwardingSettings.edit')"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                @click="confirmDelete(dest.name)"
                class="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-sm"
                :title="$t('settings.admin.logForwardingSettings.delete')"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <BaseModal
      v-model="showModal"
      :title="editingDestination ? $t('settings.admin.logForwardingSettings.editDestination') : $t('settings.admin.logForwardingSettings.addDestination')"
      width="32rem"
      :close-label="$t('settings.admin.logForwardingSettings.close')"
      @close="closeModal"
    >
      <div class="space-y-4">
      <!-- Name -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.name') }}</label>
        <input
          v-model="formData.name"
          type="text"
          :disabled="!!editingDestination"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:bg-gray-100"
          :placeholder="$t('settings.admin.logForwardingSettings.eGProductionSyslog')"
        />
      </div>

      <!-- Type -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.type') }}</label>
        <select
          v-model="formData.type"
          :disabled="!!editingDestination"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        >
          <option v-for="t in destinationTypes" :key="t.value" :value="t.value">
            {{ t.label }}
          </option>
        </select>
      </div>

      <!-- URL (every type except file; syslog takes host:port) -->
      <div v-if="formData.type !== 'file'">
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.uRL') }}</label>
        <input
          v-model="formData.url"
          type="text"
          data-test="field-url"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          :placeholder="getUrlPlaceholder(formData.type, t)"
        />
      </div>

      <div v-if="formData.type === 'syslog'">
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.protocol') }}</label>
        <select
          v-model="formData.syslog_protocol"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        >
          <option value="udp">{{ $t('settings.admin.logForwardingSettings.uDPUnreliableFast') }}</option>
          <option value="tcp">{{ $t('settings.admin.logForwardingSettings.tCPReliable') }}</option>
          <option value="tcp_tls">{{ $t('settings.admin.logForwardingSettings.tCPTLSEncrypted') }}</option>
        </select>
      </div>

      <div v-if="formData.type === 'webhook' || formData.type === 'seq'">
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.aPIKeyOptional') }}</label>
        <input
          v-model="formData.api_key"
          type="password"
          autocomplete="new-password"
          data-test="field-api-key"
          :disabled="formData.clear_api_key"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        />
        <p v-if="editingDestination" class="mt-1 text-xs text-autobot-text-tertiary">{{ $t('settings.admin.logForwardingSettings.leaveBlankToKeep') }}</p>
        <label v-if="editingDestination" class="mt-1 flex items-center gap-2 text-xs text-autobot-text-secondary">
          <input v-model="formData.clear_api_key" type="checkbox" data-test="remove-api-key" />
          {{ $t('settings.admin.logForwardingSettings.removeStoredValue') }}
        </label>
      </div>

      <div v-if="formData.type === 'file'">
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.filePath') }}</label>
        <input
          v-model="formData.file_path"
          type="text"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          :placeholder="$t('settings.admin.logForwardingSettings.varLogAutobotForwardedLog')"
        />
      </div>

      <div v-if="formData.type === 'elasticsearch'">
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.indexName') }}</label>
        <input
          v-model="formData.index"
          type="text"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          :placeholder="$t('settings.admin.logForwardingSettings.autobotLogs')"
        />
      </div>

      <div v-if="formData.type === 'elasticsearch' || formData.type === 'loki'" class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.username') }}</label>
          <input
            v-model="formData.username"
            type="text"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.password') }}</label>
          <input
            v-model="formData.password"
            type="password"
            autocomplete="new-password"
            data-test="field-password"
            :disabled="formData.clear_password"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
          <p v-if="editingDestination" class="mt-1 text-xs text-autobot-text-tertiary">{{ $t('settings.admin.logForwardingSettings.leaveBlankToKeep') }}</p>
          <label v-if="editingDestination" class="mt-1 flex items-center gap-2 text-xs text-autobot-text-secondary">
          <input v-model="formData.clear_password" type="checkbox" data-test="remove-password" />
          {{ $t('settings.admin.logForwardingSettings.removeStoredValue') }}
        </label>
        </div>
      </div>

      <!-- Common Options -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.logForwardingSettings.minimumLogLevel') }}</label>
        <select
          v-model="formData.min_level"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
        >
          <option value="Debug">{{ $t('settings.admin.logForwardingSettings.debug') }}</option>
          <option value="Information">{{ $t('settings.admin.logForwardingSettings.information') }}</option>
          <option value="Warning">{{ $t('settings.admin.logForwardingSettings.warning') }}</option>
          <option value="Error">{{ $t('settings.admin.logForwardingSettings.error') }}</option>
          <option value="Fatal">{{ $t('settings.admin.logForwardingSettings.fatal') }}</option>
        </select>
      </div>

      <!-- Enabled Toggle -->
      <div class="flex items-center gap-3 pt-2">
        <label class="relative inline-flex items-center cursor-pointer">
          <input type="checkbox" v-model="formData.enabled" class="sr-only peer" />
          <div class="w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
        </label>
        <span class="text-sm text-gray-700">{{ $t('settings.admin.logForwardingSettings.enabled') }}</span>
      </div>
      </div>
      <template #actions>
        <button
          @click="closeModal"
          class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
        >{{ $t('settings.admin.logForwardingSettings.cancel') }}</button>
        <button
          @click="saveDestination"
          :disabled="saving"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ editingDestination ? $t('settings.admin.logForwardingSettings.update') : $t('settings.admin.logForwardingSettings.create') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation -->
    <BaseModal
      :model-value="!!deleteTarget"
      :title="$t('settings.admin.logForwardingSettings.deleteDestination')"
      size="sm"
      :close-label="$t('settings.admin.logForwardingSettings.close')"
      @close="deleteTarget = null"
    >
      <p class="text-gray-600 mb-6">{{ $t('settings.admin.logForwardingSettings.areYouSureYouWantTo') }}</p>
      <template #actions>
        <button
          @click="deleteTarget = null"
          class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
        >{{ $t('settings.admin.logForwardingSettings.cancel') }}</button>
        <button
          @click="deleteDestination"
          :disabled="saving"
          class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>{{ $t('settings.admin.logForwardingSettings.delete') }}</button>
      </template>
    </BaseModal>
  </div>
</template>
