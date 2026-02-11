<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SecurityView - Security analytics and policy management
 *
 * Issue #754: Added role="tablist"/role="tab"/aria-selected on tab nav,
 * role="alert" on error messages, role="status" on loading,
 * scope="col" on all table headers, role="img" with aria-label on
 * severity dots, aria-label on filter selects, role="dialog" with
 * aria-modal/aria-labelledby on upload modal, @keydown.escape on modal,
 * aria-hidden on decorative icons, accessible button labels.
 */

import { ref, onMounted, computed } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SecurityView')
const slmApi = useSlmApi()

interface SecurityEvent {
  id: number
  event_id: string
  timestamp: string
  event_type: string
  severity: string
  title: string
  description?: string
  source_ip?: string
  source_user?: string
  is_acknowledged: boolean
  is_resolved: boolean
}

interface AuditLog {
  id: number
  log_id: string
  timestamp: string
  username?: string
  ip_address?: string
  category: string
  action: string
  resource_type?: string
  success: boolean
}

interface SecurityPolicy {
  id: number
  policy_id: string
  name: string
  description?: string
  category: string
  status: string
  is_enforced: boolean
  compliance_score?: number
  violations_count: number
}

interface SecurityOverview {
  security_score: number
  active_threats: number
  failed_logins_24h: number
  policy_violations: number
  total_events_24h: number
  critical_events: number
  certificates_expiring: number
  recent_events: SecurityEvent[]
}

interface ThreatSummary {
  total_threats: number
  critical: number
  high: number
  medium: number
  low: number
  acknowledged: number
  resolved: number
  by_type: Record<string, number>
}

interface TLSEndpoint {
  credential_id: string
  node_id: string
  hostname: string
  ip_address: string
  name: string | null
  common_name: string | null
  expires_at: string | null
  is_active: boolean
  days_until_expiry: number | null
}

// All security API calls use slmApi composable (initialized above)
const activeTab = ref('overview')
const loading = ref(false)
const error = ref<string | null>(null)

// Data
const overview = ref<SecurityOverview | null>(null)
const auditLogs = ref<AuditLog[]>([])
const auditLogsTotal = ref(0)
const securityEvents = ref<SecurityEvent[]>([])
const eventsTotal = ref(0)
const threatSummary = ref<ThreatSummary | null>(null)
const policies = ref<SecurityPolicy[]>([])
const policiesTotal = ref(0)

// TLS Certificates Data (Issue #725)
const tlsEndpoints = ref<TLSEndpoint[]>([])
const tlsEndpointsTotal = ref(0)
const tlsExpiringSoon = ref(0)
const showUploadModal = ref(false)
const selectedNodeId = ref('')
const uploadForm = ref({
  name: '',
  ca_cert: '',
  server_cert: '',
  server_key: '',
})

// Pagination
const currentPage = ref(1)
const perPage = ref(50)

// Filters
const auditCategoryFilter = ref('')
const eventSeverityFilter = ref('')

const tabs = [
  { id: 'overview', name: 'Security Overview' },
  { id: 'tls-settings', name: 'TLS Settings' },  // Issue #164
  { id: 'certificates', name: 'TLS Certificates' },
  { id: 'audit', name: 'Audit Logs' },
  { id: 'threats', name: 'Threat Detection' },
  { id: 'policies', name: 'Security Policies' },
]

// TLS Settings State (Issue #164)
interface TLSServiceStatus {
  name: string
  displayName: string
  enabled: boolean
  port: number
  description: string
}

const tlsServices = ref<TLSServiceStatus[]>([
  { name: 'frontend', displayName: 'Frontend (Vue)', enabled: false, port: 443, description: 'Web interface on 172.16.168.21' },
  { name: 'backend', displayName: 'Backend API', enabled: false, port: 8443, description: 'FastAPI backend on 172.16.168.20' },
  { name: 'redis', displayName: 'Redis', enabled: false, port: 6380, description: 'Redis data store on 172.16.168.23' },
])
const selectedTlsServices = ref<string[]>(['frontend', 'backend', 'redis'])
const deployCertsFirst = ref(true)
const tlsEnabling = ref(false)
const tlsEnableResult = ref<{
  success: boolean
  message: string
  details?: string
} | null>(null)

const severityColors: Record<string, string> = {
  low: 'bg-blue-500',
  medium: 'bg-yellow-500',
  high: 'bg-orange-500',
  critical: 'bg-red-500',
}

// Format relative time
function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
}

// API calls
async function fetchOverview() {
  try {
    loading.value = true
    const response = await slmApi.getSecurityOverview()
    overview.value = response
    logger.info('Security overview loaded')
  } catch (err) {
    logger.error('Failed to fetch security overview:', err)
    error.value = 'Failed to load security overview'
  } finally {
    loading.value = false
  }
}

async function fetchAuditLogs() {
  try {
    loading.value = true
    const response = await slmApi.getAuditLogs(
      currentPage.value,
      perPage.value,
      auditCategoryFilter.value || undefined
    )
    auditLogs.value = response.logs
    auditLogsTotal.value = response.total
    logger.info('Audit logs loaded:', response.total)
  } catch (err) {
    logger.error('Failed to fetch audit logs:', err)
    error.value = 'Failed to load audit logs'
  } finally {
    loading.value = false
  }
}

async function fetchSecurityEvents() {
  try {
    loading.value = true
    const response = await slmApi.getSecurityEvents(
      currentPage.value,
      perPage.value,
      eventSeverityFilter.value || undefined
    )
    securityEvents.value = response.events
    eventsTotal.value = response.total
    logger.info('Security events loaded:', response.total)
  } catch (err) {
    logger.error('Failed to fetch security events:', err)
    error.value = 'Failed to load security events'
  } finally {
    loading.value = false
  }
}

async function fetchThreatSummary() {
  try {
    const response = await slmApi.getThreatSummary(24)
    threatSummary.value = response
    logger.info('Threat summary loaded')
  } catch (err) {
    logger.error('Failed to fetch threat summary:', err)
  }
}

async function fetchPolicies() {
  try {
    loading.value = true
    const response = await slmApi.getSecurityPolicies(
      currentPage.value,
      perPage.value
    )
    policies.value = response.policies
    policiesTotal.value = response.total
    logger.info('Security policies loaded:', response.total)
  } catch (err) {
    logger.error('Failed to fetch security policies:', err)
    error.value = 'Failed to load security policies'
  } finally {
    loading.value = false
  }
}

// TLS Certificates functions (Issue #725)
async function fetchTlsEndpoints() {
  try {
    loading.value = true
    const response = await slmApi.getTlsEndpoints(true)
    tlsEndpoints.value = response.endpoints
    tlsEndpointsTotal.value = response.total
    tlsExpiringSoon.value = response.expiring_soon
    logger.info('TLS endpoints loaded:', response.total)
  } catch (err) {
    logger.error('Failed to fetch TLS endpoints:', err)
    error.value = 'Failed to load TLS certificates'
  } finally {
    loading.value = false
  }
}

async function deleteTlsCertificate(credentialId: string) {
  if (!confirm('Are you sure you want to delete this certificate?')) {
    return
  }

  try {
    await slmApi.deleteTlsCredential(credentialId)
    await fetchTlsEndpoints()
    logger.info('TLS certificate deleted:', credentialId)
  } catch (err) {
    logger.error('Failed to delete TLS certificate:', err)
    alert('Failed to delete certificate')
  }
}

async function toggleTlsCertificateActive(credentialId: string, currentlyActive: boolean) {
  try {
    await slmApi.updateTlsCredential(credentialId, { is_active: !currentlyActive })
    await fetchTlsEndpoints()
    logger.info('TLS certificate toggled:', credentialId)
  } catch (err) {
    logger.error('Failed to toggle TLS certificate:', err)
  }
}

const renewingCredentialId = ref<string | null>(null)
const rotatingCredentialId = ref<string | null>(null)
const bulkRenewing = ref(false)

async function renewTlsCertificate(credentialId: string) {
  if (!confirm('Renew this certificate? This will generate a new certificate with the same CN and extended validity.')) {
    return
  }

  renewingCredentialId.value = credentialId
  try {
    const result = await slmApi.renewTlsCertificate(credentialId, true)
    await fetchTlsEndpoints()
    logger.info('TLS certificate renewed:', result)
    alert(`Certificate renewed successfully. New expiry: ${result.expires_at || 'Unknown'}`)
  } catch (err) {
    logger.error('Failed to renew TLS certificate:', err)
    alert('Failed to renew certificate')
  } finally {
    renewingCredentialId.value = null
  }
}

async function rotateTlsCertificate(credentialId: string) {
  if (!confirm('Rotate this certificate? This will generate a completely new certificate with new keys (more secure than renewal).')) {
    return
  }

  rotatingCredentialId.value = credentialId
  try {
    const result = await slmApi.rotateTlsCertificate(credentialId, true, true)
    await fetchTlsEndpoints()
    logger.info('TLS certificate rotated:', result)
    alert(`Certificate rotated successfully. New expiry: ${result.expires_at || 'Unknown'}`)
  } catch (err) {
    logger.error('Failed to rotate TLS certificate:', err)
    alert('Failed to rotate certificate')
  } finally {
    rotatingCredentialId.value = null
  }
}

async function bulkRenewExpiring() {
  if (!confirm('Renew all certificates expiring within 30 days? This will deploy new certificates to the nodes.')) {
    return
  }

  bulkRenewing.value = true
  try {
    const result = await slmApi.bulkRenewExpiringCertificates(30, true)
    await fetchTlsEndpoints()
    logger.info('Bulk renewal completed:', result)
    alert(`Bulk renewal complete: ${result.renewed} renewed, ${result.failed} failed`)
  } catch (err) {
    logger.error('Failed to bulk renew certificates:', err)
    alert('Failed to bulk renew certificates')
  } finally {
    bulkRenewing.value = false
  }
}

function openUploadModal() {
  uploadForm.value = { name: '', ca_cert: '', server_cert: '', server_key: '' }
  selectedNodeId.value = ''
  showUploadModal.value = true
}

async function uploadTlsCertificate() {
  if (!selectedNodeId.value) {
    alert('Please select a node')
    return
  }
  if (!uploadForm.value.ca_cert || !uploadForm.value.server_cert || !uploadForm.value.server_key) {
    alert('Please provide all certificate files')
    return
  }

  try {
    await slmApi.createTlsCredential(selectedNodeId.value, uploadForm.value)
    showUploadModal.value = false
    await fetchTlsEndpoints()
    logger.info('TLS certificate uploaded for node:', selectedNodeId.value)
  } catch (err) {
    logger.error('Failed to upload TLS certificate:', err)
    alert('Failed to upload certificate')
  }
}

function formatExpiryStatus(daysUntil: number | null): { text: string; class: string } {
  if (daysUntil === null) return { text: 'Unknown', class: 'bg-gray-100 text-gray-700' }
  if (daysUntil <= 0) return { text: 'Expired', class: 'bg-red-100 text-red-700' }
  if (daysUntil <= 7) return { text: `${daysUntil}d`, class: 'bg-red-100 text-red-700' }
  if (daysUntil <= 30) return { text: `${daysUntil}d`, class: 'bg-yellow-100 text-yellow-700' }
  if (daysUntil <= 90) return { text: `${daysUntil}d`, class: 'bg-blue-100 text-blue-700' }
  return { text: `${daysUntil}d`, class: 'bg-green-100 text-green-700' }
}

async function acknowledgeEvent(eventId: string) {
  try {
    await slmApi.acknowledgeSecurityEvent(eventId)
    await fetchSecurityEvents()
    await fetchOverview()
    logger.info('Event acknowledged:', eventId)
  } catch (err) {
    logger.error('Failed to acknowledge event:', err)
  }
}

async function resolveEvent(eventId: string) {
  const notes = prompt('Enter resolution notes:')
  if (!notes) return

  try {
    await slmApi.resolveSecurityEvent(eventId, { resolution_notes: notes })
    await fetchSecurityEvents()
    await fetchOverview()
    logger.info('Event resolved:', eventId)
  } catch (err) {
    logger.error('Failed to resolve event:', err)
  }
}

async function togglePolicyEnforcement(policyId: string, currentlyEnforced: boolean) {
  try {
    if (currentlyEnforced) {
      await slmApi.deactivateSecurityPolicy(policyId)
    } else {
      await slmApi.activateSecurityPolicy(policyId)
    }
    await fetchPolicies()
    logger.info('Policy enforcement toggled:', policyId)
  } catch (err) {
    logger.error('Failed to toggle policy:', err)
  }
}

// TLS Settings functions (Issue #164)
function toggleTlsService(serviceName: string) {
  const index = selectedTlsServices.value.indexOf(serviceName)
  if (index === -1) {
    selectedTlsServices.value.push(serviceName)
  } else {
    selectedTlsServices.value.splice(index, 1)
  }
}

async function enableTlsOnSelectedServices() {
  if (selectedTlsServices.value.length === 0) {
    alert('Please select at least one service to enable TLS')
    return
  }

  if (!confirm(`Enable TLS on ${selectedTlsServices.value.join(', ')}?\n\nThis will:\n1. Deploy TLS certificates to the nodes\n2. Configure services for HTTPS\n3. Restart affected services\n\nContinue?`)) {
    return
  }

  tlsEnabling.value = true
  tlsEnableResult.value = null

  try {
    const result = await slmApi.enableTlsOnServices(
      selectedTlsServices.value,
      deployCertsFirst.value
    )

    tlsEnableResult.value = {
      success: result.success,
      message: result.message,
      details: result.results.enable_tls?.stdout || ''
    }

    if (result.success) {
      // Update local state to reflect enabled services
      selectedTlsServices.value.forEach(serviceName => {
        const service = tlsServices.value.find(s => s.name === serviceName)
        if (service) {
          service.enabled = true
        }
      })
    }

    logger.info('TLS enablement result:', result)
  } catch (err) {
    logger.error('Failed to enable TLS:', err)
    tlsEnableResult.value = {
      success: false,
      message: err instanceof Error ? err.message : 'Failed to enable TLS'
    }
  } finally {
    tlsEnabling.value = false
  }
}

// Watch tab changes
function onTabChange(tabId: string) {
  activeTab.value = tabId
  currentPage.value = 1
  error.value = null

  switch (tabId) {
    case 'overview':
      fetchOverview()
      break
    case 'tls-settings':
      // TLS Settings tab - no API call needed, state is local
      break
    case 'certificates':
      fetchTlsEndpoints()
      break
    case 'audit':
      fetchAuditLogs()
      break
    case 'threats':
      fetchSecurityEvents()
      fetchThreatSummary()
      break
    case 'policies':
      fetchPolicies()
      break
  }
}

// Initial load
onMounted(() => {
  fetchOverview()
})

// Computed
const scoreColor = computed(() => {
  if (!overview.value) return 'text-gray-500'
  const score = overview.value.security_score
  if (score >= 90) return 'text-success-600'
  if (score >= 70) return 'text-warning-600'
  return 'text-error-600'
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Security Analytics</h1>
      <p class="text-sm text-gray-500 mt-1">
        Monitor security events and manage security policies
      </p>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="mb-4 p-4 bg-error-50 border border-error-200 rounded-lg" role="alert">
      <p class="text-error-700">{{ error }}</p>
    </div>

    <!-- Tab Navigation -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-4" role="tablist" aria-label="Security sections">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="onTabChange(tab.id)"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          :class="[
            'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === tab.id
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          {{ tab.name }}
        </button>
      </nav>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12" role="status" aria-label="Loading security data">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" aria-hidden="true"></div>
    </div>

    <!-- Security Overview -->
    <div v-else-if="activeTab === 'overview'" role="tabpanel" aria-label="Security Overview">
      <template v-if="overview">
        <!-- Security Score -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div class="card p-4">
            <div class="text-sm text-gray-500 mb-1">Security Score</div>
            <div :class="['text-3xl font-bold', scoreColor]">{{ overview.security_score }}%</div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-gray-500 mb-1">Active Threats</div>
            <div :class="['text-3xl font-bold', overview.active_threats > 0 ? 'text-error-600' : 'text-gray-900']">
              {{ overview.active_threats }}
            </div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-gray-500 mb-1">Failed Logins (24h)</div>
            <div :class="['text-3xl font-bold', overview.failed_logins_24h > 5 ? 'text-warning-600' : 'text-gray-900']">
              {{ overview.failed_logins_24h }}
            </div>
          </div>
          <div class="card p-4">
            <div class="text-sm text-gray-500 mb-1">Policy Violations</div>
            <div :class="['text-3xl font-bold', overview.policy_violations > 0 ? 'text-warning-600' : 'text-gray-900']">
              {{ overview.policy_violations }}
            </div>
          </div>
        </div>

        <!-- Recent Events -->
        <div class="card">
          <div class="px-6 py-4 border-b border-gray-200">
            <h2 class="text-lg font-semibold">Recent Security Events</h2>
          </div>
          <div v-if="overview.recent_events.length === 0" class="p-6 text-center text-gray-500">
            No recent security events
          </div>
          <div v-else class="divide-y divide-gray-200">
            <div
              v-for="event in overview.recent_events"
              :key="event.event_id"
              class="px-6 py-4 flex items-center justify-between"
            >
              <div class="flex items-center gap-3">
                <div
                  :class="['w-2 h-2 rounded-full', severityColors[event.severity] || 'bg-gray-500']"
                  role="img"
                  :aria-label="`${event.severity} severity`"
                ></div>
                <div>
                  <div class="text-sm font-medium text-gray-900">{{ event.title }}</div>
                  <div class="text-xs text-gray-500">
                    {{ event.source_user ? `User: ${event.source_user}` : '' }}
                    {{ event.source_ip ? ` | IP: ${event.source_ip}` : '' }}
                  </div>
                </div>
              </div>
              <div class="text-xs text-gray-500">{{ formatRelativeTime(event.timestamp) }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- TLS Settings (Issue #164) -->
    <div v-else-if="activeTab === 'tls-settings'" role="tabpanel" aria-label="TLS Settings">
      <!-- Header -->
      <div class="mb-6">
        <h2 class="text-lg font-semibold text-gray-900">TLS/HTTPS Configuration</h2>
        <p class="text-sm text-gray-500 mt-1">
          Enable TLS encryption for AutoBot services. This will configure HTTPS for web services and TLS for Redis.
        </p>
      </div>

      <!-- Result Alert -->
      <div
        v-if="tlsEnableResult"
        :class="['mb-6 p-4 rounded-lg border', tlsEnableResult.success ? 'bg-success-50 border-success-200' : 'bg-error-50 border-error-200']"
        :role="tlsEnableResult.success ? 'status' : 'alert'"
      >
        <div class="flex items-start gap-3">
          <svg v-if="tlsEnableResult.success" class="w-5 h-5 text-success-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <svg v-else class="w-5 h-5 text-error-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p :class="tlsEnableResult.success ? 'text-success-700' : 'text-error-700'">
              {{ tlsEnableResult.message }}
            </p>
            <details v-if="tlsEnableResult.details" class="mt-2">
              <summary class="text-sm text-gray-600 cursor-pointer">Show details</summary>
              <pre class="mt-2 text-xs bg-white p-3 rounded border overflow-x-auto max-h-48">{{ tlsEnableResult.details }}</pre>
            </details>
          </div>
          <button @click="tlsEnableResult = null" class="ml-auto text-gray-400 hover:text-gray-600" aria-label="Dismiss TLS result">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Services Selection -->
      <div class="card mb-6">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-base font-semibold">Select Services to Enable TLS</h3>
        </div>
        <div class="p-6">
          <div class="space-y-4" role="group" aria-label="TLS service selection">
            <div
              v-for="service in tlsServices"
              :key="service.name"
              class="flex items-center justify-between p-4 rounded-lg border hover:bg-gray-50 cursor-pointer"
              :class="selectedTlsServices.includes(service.name) ? 'border-primary-300 bg-primary-50' : 'border-gray-200'"
              @click="toggleTlsService(service.name)"
            >
              <div class="flex items-center gap-4">
                <input
                  type="checkbox"
                  :checked="selectedTlsServices.includes(service.name)"
                  class="h-5 w-5 text-primary-600 rounded border-gray-300 focus:ring-primary-500"
                  :aria-label="`Enable TLS for ${service.displayName}`"
                  @click.stop
                  @change="toggleTlsService(service.name)"
                />
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-gray-900">{{ service.displayName }}</span>
                    <span
                      :class="[
                        'px-2 py-0.5 rounded-full text-xs',
                        service.enabled ? 'bg-success-100 text-success-700' : 'bg-gray-100 text-gray-600'
                      ]"
                    >
                      {{ service.enabled ? 'TLS Enabled' : 'HTTP' }}
                    </span>
                  </div>
                  <p class="text-sm text-gray-500 mt-0.5">{{ service.description }}</p>
                </div>
              </div>
              <div class="text-right">
                <div class="text-sm font-mono text-gray-600">Port {{ service.port }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Options -->
      <div class="card mb-6">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-base font-semibold">Options</h3>
        </div>
        <div class="p-6">
          <label class="flex items-center gap-3 cursor-pointer">
            <input
              v-model="deployCertsFirst"
              type="checkbox"
              class="h-5 w-5 text-primary-600 rounded border-gray-300 focus:ring-primary-500"
            />
            <div>
              <span class="font-medium text-gray-900">Deploy certificates first</span>
              <p class="text-sm text-gray-500">Distribute TLS certificates to nodes before enabling TLS. Recommended for first-time setup.</p>
            </div>
          </label>
        </div>
      </div>

      <!-- Action Button -->
      <div class="flex justify-end">
        <button
          @click="enableTlsOnSelectedServices"
          :disabled="tlsEnabling || selectedTlsServices.length === 0"
          :class="[
            'px-6 py-3 rounded-lg font-medium text-white transition-colors flex items-center gap-2',
            tlsEnabling || selectedTlsServices.length === 0
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-primary-600 hover:bg-primary-700'
          ]"
        >
          <svg v-if="tlsEnabling" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          {{ tlsEnabling ? 'Enabling TLS...' : `Enable TLS on ${selectedTlsServices.length} Service${selectedTlsServices.length !== 1 ? 's' : ''}` }}
        </button>
      </div>

      <!-- Help Section -->
      <div class="mt-8 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <div class="flex items-start gap-3">
          <svg class="w-5 h-5 text-blue-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div class="text-sm text-blue-800">
            <p class="font-medium mb-1">What happens when you enable TLS?</p>
            <ul class="list-disc list-inside space-y-1 text-blue-700">
              <li>TLS certificates are deployed to the selected nodes</li>
              <li>Service configurations are updated to use HTTPS/TLS</li>
              <li>Services are restarted to apply the changes</li>
              <li>Frontend will be accessible at https://172.16.168.21:443</li>
              <li>Backend API will be accessible at https://172.16.168.20:8443</li>
              <li>Redis will accept TLS connections on port 6380</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- TLS Certificates (Issue #725) -->
    <div v-else-if="activeTab === 'certificates'" role="tabpanel" aria-label="TLS Certificates">
      <!-- Summary Cards -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Total Certificates</div>
          <div class="text-3xl font-bold text-gray-900">{{ tlsEndpointsTotal }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Active</div>
          <div class="text-3xl font-bold text-success-600">
            {{ tlsEndpoints.filter(e => e.is_active).length }}
          </div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Expiring Soon (30d)</div>
          <div :class="['text-3xl font-bold', tlsExpiringSoon > 0 ? 'text-warning-600' : 'text-gray-900']">
            {{ tlsExpiringSoon }}
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="mb-4 flex justify-end gap-3">
        <button
          v-if="tlsExpiringSoon > 0"
          @click="bulkRenewExpiring"
          :disabled="bulkRenewing"
          class="btn btn-secondary"
        >
          {{ bulkRenewing ? 'Renewing...' : `Renew Expiring (${tlsExpiringSoon})` }}
        </button>
        <button
          @click="openUploadModal"
          class="btn btn-primary"
        >
          Upload Certificate
        </button>
      </div>

      <!-- Certificates Table -->
      <div class="card overflow-hidden">
        <div v-if="tlsEndpoints.length === 0" class="p-6 text-center text-gray-500">
          No TLS certificates found. Click "Upload Certificate" to add one.
        </div>
        <table v-else class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Common Name</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expiry</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="endpoint in tlsEndpoints" :key="endpoint.credential_id">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="text-sm font-medium text-gray-900">{{ endpoint.hostname }}</div>
                <div class="text-xs text-gray-500">{{ endpoint.ip_address }}</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ endpoint.name || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                {{ endpoint.common_name || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs font-medium',
                    formatExpiryStatus(endpoint.days_until_expiry).class
                  ]"
                >
                  {{ formatExpiryStatus(endpoint.days_until_expiry).text }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="[
                    'px-2 py-1 rounded-full text-xs',
                    endpoint.is_active ? 'bg-success-100 text-success-700' : 'bg-gray-100 text-gray-700'
                  ]"
                >
                  {{ endpoint.is_active ? 'Active' : 'Inactive' }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">
                <div class="flex gap-2 flex-wrap">
                  <button
                    @click="renewTlsCertificate(endpoint.credential_id)"
                    :disabled="renewingCredentialId === endpoint.credential_id"
                    class="px-2 py-1 rounded text-xs bg-blue-100 hover:bg-blue-200 text-blue-700 disabled:opacity-50"
                    :aria-label="`Renew certificate for ${endpoint.hostname}`"
                  >
                    {{ renewingCredentialId === endpoint.credential_id ? '...' : 'Renew' }}
                  </button>
                  <button
                    @click="rotateTlsCertificate(endpoint.credential_id)"
                    :disabled="rotatingCredentialId === endpoint.credential_id"
                    class="px-2 py-1 rounded text-xs bg-purple-100 hover:bg-purple-200 text-purple-700 disabled:opacity-50"
                    :aria-label="`Rotate certificate for ${endpoint.hostname}`"
                  >
                    {{ rotatingCredentialId === endpoint.credential_id ? '...' : 'Rotate' }}
                  </button>
                  <button
                    @click="toggleTlsCertificateActive(endpoint.credential_id, endpoint.is_active)"
                    :class="[
                      'px-2 py-1 rounded text-xs',
                      endpoint.is_active
                        ? 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                        : 'bg-success-100 hover:bg-success-200 text-success-700'
                    ]"
                    :aria-label="`${endpoint.is_active ? 'Disable' : 'Enable'} certificate for ${endpoint.hostname}`"
                  >
                    {{ endpoint.is_active ? 'Disable' : 'Enable' }}
                  </button>
                  <button
                    @click="deleteTlsCertificate(endpoint.credential_id)"
                    class="px-2 py-1 rounded text-xs bg-error-100 hover:bg-error-200 text-error-700"
                    :aria-label="`Delete certificate for ${endpoint.hostname}`"
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Audit Logs -->
    <div v-else-if="activeTab === 'audit'" role="tabpanel" aria-label="Audit Logs">
      <!-- Filters -->
      <div class="mb-4 flex gap-4">
        <label for="audit-category-filter" class="sr-only">Filter by category</label>
        <select
          id="audit-category-filter"
          v-model="auditCategoryFilter"
          @change="fetchAuditLogs()"
          class="rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
        >
          <option value="">All Categories</option>
          <option value="authentication">Authentication</option>
          <option value="authorization">Authorization</option>
          <option value="configuration">Configuration</option>
          <option value="deployment">Deployment</option>
          <option value="node_management">Node Management</option>
          <option value="service_control">Service Control</option>
          <option value="security">Security</option>
        </select>
      </div>

      <!-- Logs Table -->
      <div class="card overflow-hidden">
        <div v-if="auditLogs.length === 0" class="p-6 text-center text-gray-500">
          No audit logs found
        </div>
        <table v-else class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Time</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Resource</th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="log in auditLogs" :key="log.log_id">
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatRelativeTime(log.timestamp) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ log.username || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">
                <span class="px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-700">
                  {{ log.category }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ log.action }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ log.resource_type || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="[
                    'px-2 py-1 rounded-full text-xs',
                    log.success ? 'bg-success-100 text-success-700' : 'bg-error-100 text-error-700'
                  ]"
                >
                  {{ log.success ? 'Success' : 'Failed' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="auditLogsTotal > perPage" class="px-6 py-4 border-t border-gray-200 text-sm text-gray-500" role="status">
          Showing {{ auditLogs.length }} of {{ auditLogsTotal }} logs
        </div>
      </div>
    </div>

    <!-- Threat Detection -->
    <div v-else-if="activeTab === 'threats'" role="tabpanel" aria-label="Threat Detection">
      <!-- Summary Cards -->
      <div v-if="threatSummary" class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Total (24h)</div>
          <div class="text-2xl font-bold text-gray-900">{{ threatSummary.total_threats }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Critical</div>
          <div class="text-2xl font-bold text-error-600">{{ threatSummary.critical }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">High</div>
          <div class="text-2xl font-bold text-orange-600">{{ threatSummary.high }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Medium</div>
          <div class="text-2xl font-bold text-warning-600">{{ threatSummary.medium }}</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Resolved</div>
          <div class="text-2xl font-bold text-success-600">{{ threatSummary.resolved }}</div>
        </div>
      </div>

      <!-- Filters -->
      <div class="mb-4 flex gap-4">
        <label for="event-severity-filter" class="sr-only">Filter by severity</label>
        <select
          id="event-severity-filter"
          v-model="eventSeverityFilter"
          @change="fetchSecurityEvents()"
          class="rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <!-- Events List -->
      <div class="card">
        <div v-if="securityEvents.length === 0" class="p-6 text-center text-gray-500">
          No security events found
        </div>
        <div v-else class="divide-y divide-gray-200">
          <div
            v-for="event in securityEvents"
            :key="event.event_id"
            class="p-4 hover:bg-gray-50"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-start gap-3">
                <div
                  :class="['w-3 h-3 mt-1 rounded-full', severityColors[event.severity]]"
                  role="img"
                  :aria-label="`${event.severity} severity`"
                ></div>
                <div>
                  <div class="font-medium text-gray-900">{{ event.title }}</div>
                  <div class="text-sm text-gray-500 mt-1">{{ event.description || 'No description' }}</div>
                  <div class="text-xs text-gray-400 mt-2">
                    {{ event.source_ip ? `IP: ${event.source_ip}` : '' }}
                    {{ event.source_user ? ` | User: ${event.source_user}` : '' }}
                    | {{ formatRelativeTime(event.timestamp) }}
                  </div>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs',
                    event.is_resolved
                      ? 'bg-success-100 text-success-700'
                      : event.is_acknowledged
                      ? 'bg-warning-100 text-warning-700'
                      : 'bg-gray-100 text-gray-700'
                  ]"
                >
                  {{ event.is_resolved ? 'Resolved' : event.is_acknowledged ? 'Acknowledged' : 'New' }}
                </span>
                <div v-if="!event.is_resolved" class="flex gap-1">
                  <button
                    v-if="!event.is_acknowledged"
                    @click="acknowledgeEvent(event.event_id)"
                    class="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
                    :aria-label="`Acknowledge event: ${event.title}`"
                  >
                    Ack
                  </button>
                  <button
                    @click="resolveEvent(event.event_id)"
                    class="px-2 py-1 text-xs bg-success-100 hover:bg-success-200 text-success-700 rounded"
                    :aria-label="`Resolve event: ${event.title}`"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="eventsTotal > perPage" class="px-6 py-4 border-t border-gray-200 text-sm text-gray-500" role="status">
          Showing {{ securityEvents.length }} of {{ eventsTotal }} events
        </div>
      </div>
    </div>

    <!-- Security Policies -->
    <div v-else-if="activeTab === 'policies'" role="tabpanel" aria-label="Security Policies">
      <!-- Policies List -->
      <div class="card">
        <div v-if="policies.length === 0" class="p-6 text-center text-gray-500">
          No security policies configured. Create your first policy to get started.
        </div>
        <div v-else class="divide-y divide-gray-200">
          <div
            v-for="policy in policies"
            :key="policy.policy_id"
            class="p-4 hover:bg-gray-50"
          >
            <div class="flex items-start justify-between">
              <div>
                <div class="font-medium text-gray-900">{{ policy.name }}</div>
                <div class="text-sm text-gray-500 mt-1">{{ policy.description || 'No description' }}</div>
                <div class="flex items-center gap-4 mt-2 text-xs text-gray-400">
                  <span>Category: {{ policy.category }}</span>
                  <span v-if="policy.compliance_score !== null">
                    Compliance: {{ policy.compliance_score?.toFixed(1) }}%
                  </span>
                  <span v-if="policy.violations_count > 0" class="text-warning-600">
                    {{ policy.violations_count }} violations
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs',
                    policy.status === 'active'
                      ? 'bg-success-100 text-success-700'
                      : policy.status === 'inactive'
                      ? 'bg-gray-100 text-gray-700'
                      : 'bg-warning-100 text-warning-700'
                  ]"
                >
                  {{ policy.status }}
                </span>
                <button
                  @click="togglePolicyEnforcement(policy.policy_id, policy.is_enforced)"
                  :class="[
                    'px-3 py-1 text-xs rounded',
                    policy.is_enforced
                      ? 'bg-error-100 hover:bg-error-200 text-error-700'
                      : 'bg-success-100 hover:bg-success-200 text-success-700'
                  ]"
                  :aria-label="`${policy.is_enforced ? 'Disable' : 'Enable'} policy: ${policy.name}`"
                >
                  {{ policy.is_enforced ? 'Disable' : 'Enable' }}
                </button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="policiesTotal > perPage" class="px-6 py-4 border-t border-gray-200 text-sm text-gray-500" role="status">
          Showing {{ policies.length }} of {{ policiesTotal }} policies
        </div>
      </div>
    </div>

    <!-- Upload Certificate Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div
          v-if="showUploadModal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          @click.self="showUploadModal = false"
          @keydown.escape="showUploadModal = false"
          role="dialog"
          aria-modal="true"
          aria-labelledby="upload-cert-title"
        >
          <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 id="upload-cert-title" class="text-lg font-semibold text-gray-900">Upload TLS Certificate</h3>
              <button
                @click="showUploadModal = false"
                class="text-gray-400 hover:text-gray-600"
                aria-label="Close upload dialog"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="p-6 space-y-4">
              <div>
                <label for="cert-node-id" class="block text-sm font-medium text-gray-700 mb-1">Node ID</label>
                <input
                  id="cert-node-id"
                  v-model="selectedNodeId"
                  type="text"
                  placeholder="Enter node ID"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                />
              </div>

              <div>
                <label for="cert-name" class="block text-sm font-medium text-gray-700 mb-1">Certificate Name (optional)</label>
                <input
                  id="cert-name"
                  v-model="uploadForm.name"
                  type="text"
                  placeholder="e.g., redis-server, api-client"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                />
              </div>

              <div>
                <label for="cert-ca" class="block text-sm font-medium text-gray-700 mb-1">CA Certificate (PEM)</label>
                <textarea
                  id="cert-ca"
                  v-model="uploadForm.ca_cert"
                  rows="4"
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 font-mono text-xs"
                ></textarea>
              </div>

              <div>
                <label for="cert-server" class="block text-sm font-medium text-gray-700 mb-1">Server Certificate (PEM)</label>
                <textarea
                  id="cert-server"
                  v-model="uploadForm.server_cert"
                  rows="4"
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 font-mono text-xs"
                ></textarea>
              </div>

              <div>
                <label for="cert-key" class="block text-sm font-medium text-gray-700 mb-1">Private Key (PEM)</label>
                <textarea
                  id="cert-key"
                  v-model="uploadForm.server_key"
                  rows="4"
                  placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
                  class="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 font-mono text-xs"
                ></textarea>
                <p class="text-xs text-gray-500 mt-1">The private key will be encrypted before storage.</p>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button
                @click="showUploadModal = false"
                class="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                @click="uploadTlsCertificate"
                class="btn btn-primary"
              >
                Upload
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* Screen reader only utility (Issue #754) */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
