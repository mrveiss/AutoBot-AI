<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeLifecyclePanel - Displays node lifecycle events and update management
 *
 * Features:
 * - Update status section with check/install capabilities
 * - oVirt-style events table with filtering
 * - Severity-based color coding (info, warning, error, critical)
 * - Auto-refresh with polling support
 * - WebSocket integration for real-time updates
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NodeLifecyclePanel')

// Types
type EventType =
  | 'enrollment_started'
  | 'enrollment_completed'
  | 'deployment_started'
  | 'deployment_completed'
  | 'health_check_failed'
  | 'update_applied'
  | 'certificate_renewed'
  | 'status_change'
  | 'maintenance_start'
  | 'maintenance_end'
  | 'connection_test'
  | 'role_change'

type SeverityLevel = 'info' | 'warning' | 'error' | 'critical'

interface LifecycleEvent {
  id: string
  event_type: EventType | string
  timestamp: string
  message: string
  details?: Record<string, unknown>
  severity: SeverityLevel
  duration_ms?: number
}

interface AvailableUpdate {
  id: string
  version: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  size_bytes?: number
  release_date?: string
}

interface UpdatesInfo {
  count: number
  security: number
  updates: AvailableUpdate[]
}

interface EventFilters {
  event_type?: string
  severity?: string
  limit?: number
  offset?: number
}

// Props
interface Props {
  nodeId: string
  nodeName?: string
  autoRefreshInterval?: number // in milliseconds, default 5000
}

const props = withDefaults(defineProps<Props>(), {
  nodeName: 'Node',
  autoRefreshInterval: 5000,
})

// Emits
const emit = defineEmits<{
  close: []
  updateApplied: [updateIds: string[]]
}>()

// API composable (methods will be added later)
const api = useSlmApi()

// State
const events = ref<LifecycleEvent[]>([])
const totalEvents = ref(0)
const isLoading = ref(true)
const isLoadingMore = ref(false)
const currentOperation = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)

// Update state
const availableUpdates = ref<UpdatesInfo | null>(null)
const isCheckingUpdates = ref(false)
const isInstallingUpdates = ref(false)
const updateProgress = ref(0)
const selectedUpdateIds = ref<string[]>([])

// Filter state
const eventTypeFilter = ref<string>('all')
const severityFilter = ref<string>('all')
const autoRefresh = ref(true)

// Pagination
const pageSize = 50
const currentOffset = ref(0)
const hasMore = computed(() => events.value.length < totalEvents.value)

// WebSocket connection
let ws: WebSocket | null = null
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Event type options
const eventTypeOptions = [
  { value: 'all', label: 'All Events' },
  { value: 'enrollment', label: 'Enrollment' },
  { value: 'deployment', label: 'Deployment' },
  { value: 'health', label: 'Health Checks' },
  { value: 'remediation', label: 'Remediation' },
  { value: 'rollback', label: 'Rollback' },
  { value: 'update', label: 'Updates' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'certificate', label: 'Certificates' },
]

// Severity options
const severityOptions = [
  { value: 'all', label: 'All Severities' },
  { value: 'info', label: 'Info' },
  { value: 'warning', label: 'Warning' },
  { value: 'error', label: 'Error' },
  { value: 'critical', label: 'Critical' },
]

// Computed
const filteredEvents = computed(() => {
  return events.value.filter((event) => {
    // Event type filter
    if (eventTypeFilter.value !== 'all') {
      const category = getEventCategory(event.event_type)
      if (category !== eventTypeFilter.value) return false
    }

    // Severity filter
    if (severityFilter.value !== 'all') {
      if (event.severity !== severityFilter.value) return false
    }

    return true
  })
})

const updatesSummary = computed(() => {
  if (!availableUpdates.value) return null
  const { count, security, updates } = availableUpdates.value
  const critical = updates.filter((u) => u.severity === 'critical').length
  return { count, security, critical }
})

// Methods
function getEventCategory(eventType: string): string {
  if (eventType.includes('enrollment')) return 'enrollment'
  if (eventType.includes('deployment')) return 'deployment'
  if (eventType.includes('rollback')) return 'rollback'
  if (eventType.includes('health')) return 'health'
  if (eventType.includes('update')) return 'update'
  if (eventType.includes('maintenance')) return 'maintenance'
  if (eventType.includes('certificate')) return 'certificate'
  if (eventType.includes('remediation')) return 'remediation'
  if (eventType.includes('state_change')) return 'health'
  if (eventType.includes('manual_action')) return 'maintenance'
  return 'other'
}

function getSeverityIcon(severity: SeverityLevel): string {
  const icons: Record<SeverityLevel, string> = {
    info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    warning:
      'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
    error: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
    critical:
      'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  }
  return icons[severity] || icons.info
}

function getSeverityClasses(severity: SeverityLevel): {
  bg: string
  text: string
  icon: string
} {
  const classes: Record<SeverityLevel, { bg: string; text: string; icon: string }> = {
    info: {
      bg: 'bg-blue-50',
      text: 'text-blue-600',
      icon: 'text-blue-500',
    },
    warning: {
      bg: 'bg-yellow-50',
      text: 'text-yellow-700',
      icon: 'text-yellow-500',
    },
    error: {
      bg: 'bg-red-50',
      text: 'text-red-600',
      icon: 'text-red-500',
    },
    critical: {
      bg: 'bg-red-100',
      text: 'text-red-800',
      icon: 'text-red-600',
    },
  }
  return classes[severity] || classes.info
}

function getEventIcon(eventType: string): string {
  const icons: Record<string, string> = {
    enrollment_started:
      'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z',
    enrollment_completed:
      'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    deployment_started:
      'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12',
    deployment_completed: 'M5 13l4 4L19 7',
    health_check_failed:
      'M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z',
    update_applied:
      'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    certificate_renewed:
      'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
    status_change:
      'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
    maintenance_start: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z',
    maintenance_end: 'M5 13l4 4L19 7',
    connection_test:
      'M13 10V3L4 14h7v7l9-11h-7z',
    role_change:
      'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
  }
  return (
    icons[eventType] ||
    'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
  )
}

function formatEventType(eventType: string): string {
  return eventType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 60000) {
    return 'Just now'
  } else if (diffMs < 3600000) {
    const mins = Math.floor(diffMs / 60000)
    return `${mins} minute${mins === 1 ? '' : 's'} ago`
  } else if (diffMs < 86400000) {
    const hours = Math.floor(diffMs / 3600000)
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  } else {
    const days = Math.floor(diffMs / 86400000)
    return `${days} day${days === 1 ? '' : 's'} ago`
  }
}

function formatFullTime(timestamp: string): string {
  const date = new Date(timestamp)
  return (
    date.toLocaleDateString() +
    ' ' +
    date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`
  } else {
    const mins = Math.floor(ms / 60000)
    const secs = Math.floor((ms % 60000) / 1000)
    return `${mins}m ${secs}s`
  }
}

function formatDetailKey(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function getUpdateSeverityClass(severity: string): string {
  const classes: Record<string, string> = {
    low: 'bg-gray-100 text-gray-700',
    medium: 'bg-blue-100 text-blue-700',
    high: 'bg-yellow-100 text-yellow-700',
    critical: 'bg-red-100 text-red-700',
  }
  return classes[severity] || classes.low
}

// API Methods - wired to real backend endpoints
async function fetchEvents(): Promise<void> {
  try {
    const filters: EventFilters = {
      limit: pageSize,
      offset: 0,
    }
    // Note: Don't send event_type filter to API - we filter by category client-side
    // The API expects exact event types (e.g., 'deployment_completed') but UI filters
    // by category (e.g., 'deployment'). Client-side filteredEvents handles this.
    if (severityFilter.value !== 'all') {
      filters.severity = severityFilter.value
    }

    const nodeEvents = await api.getNodeEvents(props.nodeId, {
      severity: filters.severity as import('@/types/slm').EventSeverity | undefined,
      limit: filters.limit,
      offset: filters.offset,
    })

    // Map backend events to local LifecycleEvent type
    events.value = nodeEvents.map((e) => ({
      id: e.id,
      event_type: e.type,
      timestamp: e.timestamp,
      message: e.message,
      details: e.details as Record<string, unknown>,
      severity: e.severity as SeverityLevel,
    }))
    totalEvents.value = events.value.length
    currentOffset.value = events.value.length
    lastRefresh.value = new Date().toISOString()
  } catch (error) {
    logger.error('Failed to fetch lifecycle events:', error)
    // Fallback to mock data if API fails
    events.value = generateMockEvents()
    totalEvents.value = events.value.length
    currentOffset.value = events.value.length
    lastRefresh.value = new Date().toISOString()
  } finally {
    isLoading.value = false
  }
}

async function loadMoreEvents(): Promise<void> {
  if (isLoadingMore.value || !hasMore.value) return

  isLoadingMore.value = true
  try {
    const filters: EventFilters = {
      limit: pageSize,
      offset: currentOffset.value,
    }
    // Note: Don't send event_type filter to API - we filter by category client-side
    if (severityFilter.value !== 'all') {
      filters.severity = severityFilter.value
    }

    const nodeEvents = await api.getNodeEvents(props.nodeId, {
      severity: filters.severity as import('@/types/slm').EventSeverity | undefined,
      limit: filters.limit,
      offset: filters.offset,
    })

    const mappedEvents = nodeEvents.map((e) => ({
      id: e.id,
      event_type: e.type,
      timestamp: e.timestamp,
      message: e.message,
      details: e.details as Record<string, unknown>,
      severity: e.severity as SeverityLevel,
    }))

    events.value.push(...mappedEvents)
    currentOffset.value += mappedEvents.length
  } catch (error) {
    logger.error('Failed to load more events:', error)
  } finally {
    isLoadingMore.value = false
  }
}

async function checkForUpdates(): Promise<void> {
  isCheckingUpdates.value = true
  try {
    const updates = await api.checkUpdates(props.nodeId)

    // Map backend response to local UpdatesInfo format
    // Backend returns update_id, frontend type has id
    const securityCount = updates.filter((u) => u.severity === 'critical' || u.severity === 'high').length
    availableUpdates.value = {
      count: updates.length,
      security: securityCount,
      updates: updates.map((u) => ({
        id: u.id,
        version: u.version,
        description: u.description,
        severity: u.severity as 'low' | 'medium' | 'high' | 'critical',
      })),
    }
  } catch (error) {
    logger.error('Failed to check for updates:', error)
    // Show empty updates if API fails
    availableUpdates.value = { count: 0, security: 0, updates: [] }
  } finally {
    isCheckingUpdates.value = false
  }
}

async function installUpdates(): Promise<void> {
  if (!availableUpdates.value || availableUpdates.value.count === 0) return

  const updateIds =
    selectedUpdateIds.value.length > 0
      ? selectedUpdateIds.value
      : availableUpdates.value.updates.map((u) => u.id)

  isInstallingUpdates.value = true
  updateProgress.value = 0

  try {
    // Call backend API to apply updates
    const result = await api.applyUpdates(props.nodeId, updateIds)

    // Show progress animation
    const progressInterval = setInterval(() => {
      updateProgress.value += 10
      if (updateProgress.value >= 100) {
        clearInterval(progressInterval)
        isInstallingUpdates.value = false
        updateProgress.value = 0

        // Remove applied updates from the list
        if (availableUpdates.value) {
          availableUpdates.value.updates = availableUpdates.value.updates.filter(
            (u) => !result.applied_updates.includes(u.id)
          )
          availableUpdates.value.count = availableUpdates.value.updates.length
          availableUpdates.value.security = availableUpdates.value.updates.filter(
            (u) => u.severity === 'critical' || u.severity === 'high'
          ).length
        }

        selectedUpdateIds.value = []
        emit('updateApplied', result.applied_updates)
        fetchEvents() // Refresh events to show update applied

        if (result.failed_updates.length > 0) {
          logger.warn('Some updates failed to apply:', result.failed_updates)
        }
      }
    }, 500)
  } catch (error) {
    logger.error('Failed to install updates:', error)
    isInstallingUpdates.value = false
    updateProgress.value = 0
  }
}

function toggleUpdateSelection(updateId: string): void {
  const index = selectedUpdateIds.value.indexOf(updateId)
  if (index === -1) {
    selectedUpdateIds.value.push(updateId)
  } else {
    selectedUpdateIds.value.splice(index, 1)
  }
}

function selectAllUpdates(): void {
  if (!availableUpdates.value) return
  selectedUpdateIds.value = availableUpdates.value.updates.map((u) => u.id)
}

function deselectAllUpdates(): void {
  selectedUpdateIds.value = []
}

// WebSocket connection for real-time node lifecycle events (Issue #813)
function connectWebSocket(): void {
  const config = getConfig()
  const wsUrl = `${config.wsBaseUrl}/api/ws/nodes/${props.nodeId}`

  try {
    ws = new WebSocket(wsUrl)
  } catch (err) {
    logger.debug('WebSocket connection failed, using REST polling:', err)
    return
  }

  ws.onopen = () => {
    logger.info('WebSocket connected for node:', props.nodeId)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'ping' || data.type === 'connected') return
      handleWebSocketEvent(data)
    } catch (err) {
      logger.error('Failed to parse WebSocket message:', err)
    }
  }

  ws.onclose = () => {
    logger.debug('WebSocket disconnected for node:', props.nodeId)
    ws = null
  }

  ws.onerror = () => {
    logger.debug('WebSocket error, falling back to REST polling')
  }
}

function handleWebSocketEvent(data: Record<string, unknown>): void {
  const eventType = String(data.type || 'unknown')
  const eventData = (data.data || {}) as Record<string, unknown>

  const newEvent: LifecycleEvent = {
    id: `ws-${Date.now()}`,
    event_type: eventType as EventType,
    timestamp: new Date().toISOString(),
    message: String(eventData.message || `${eventType} event received`),
    severity: mapEventSeverity(eventType),
    details: eventData,
  }

  events.value.unshift(newEvent)
  totalEvents.value += 1
}

function mapEventSeverity(eventType: string): SeverityLevel {
  if (eventType.includes('failed') || eventType.includes('error')) return 'error'
  if (eventType.includes('warning') || eventType.includes('degraded')) return 'warning'
  if (eventType.includes('critical')) return 'critical'
  return 'info'
}

// Mock data generator for development
function generateMockEvents(): LifecycleEvent[] {
  const eventTypes: EventType[] = [
    'enrollment_started',
    'enrollment_completed',
    'deployment_started',
    'deployment_completed',
    'health_check_failed',
    'update_applied',
    'certificate_renewed',
    'status_change',
    'maintenance_start',
    'maintenance_end',
  ]

  const severities: SeverityLevel[] = ['info', 'warning', 'error', 'critical']

  const mockEvents: LifecycleEvent[] = []
  const now = new Date()

  for (let i = 0; i < 15; i++) {
    const eventType = eventTypes[Math.floor(Math.random() * eventTypes.length)]
    let severity: SeverityLevel = 'info'

    // Set appropriate severity based on event type
    if (eventType.includes('failed') || eventType.includes('error')) {
      severity = Math.random() > 0.5 ? 'error' : 'critical'
    } else if (eventType.includes('completed') || eventType.includes('renewed')) {
      severity = 'info'
    } else if (eventType.includes('started') || eventType.includes('change')) {
      severity = Math.random() > 0.7 ? 'warning' : 'info'
    }

    const timestamp = new Date(now.getTime() - i * 300000 - Math.random() * 300000)

    mockEvents.push({
      id: `evt-${Date.now()}-${i}`,
      event_type: eventType,
      timestamp: timestamp.toISOString(),
      message: `${formatEventType(eventType)} for node ${props.nodeName}`,
      severity,
      duration_ms: Math.random() > 0.5 ? Math.floor(Math.random() * 60000) : undefined,
      details:
        Math.random() > 0.6
          ? {
              version: '1.0.0',
              previous_status: 'healthy',
              new_status: 'degraded',
            }
          : undefined,
    })
  }

  return mockEvents.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )
}

// Watch for filter changes
watch([eventTypeFilter, severityFilter], () => {
  currentOffset.value = 0
  fetchEvents()
})

// Watch for auto-refresh changes
watch(autoRefresh, (enabled) => {
  if (enabled) {
    refreshInterval = setInterval(fetchEvents, props.autoRefreshInterval)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

// Lifecycle
onMounted(() => {
  fetchEvents()
  connectWebSocket()

  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchEvents, props.autoRefreshInterval)
  }
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col max-h-[600px]">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
      <div class="flex items-center gap-3">
        <h3 class="text-lg font-semibold text-gray-900">{{ nodeName }} - Lifecycle Events</h3>
        <div v-if="currentOperation" class="flex items-center gap-2 text-sm text-primary-600">
          <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>{{ currentOperation }}</span>
        </div>
      </div>
      <button
        @click="emit('close')"
        class="text-gray-400 hover:text-gray-600 transition-colors"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Updates Section -->
    <div class="px-4 py-3 bg-gray-50 border-b border-gray-200">
      <div class="flex items-center justify-between">
        <!-- Update Status -->
        <div class="flex items-center gap-3">
          <template v-if="updatesSummary && updatesSummary.count > 0">
            <div class="flex items-center gap-2 text-warning-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 11l5-5m0 0l5 5m-5-5v12" />
              </svg>
              <span class="font-medium">{{ updatesSummary.count }} update{{ updatesSummary.count === 1 ? '' : 's' }} available</span>
            </div>
            <span v-if="updatesSummary.security > 0" class="text-sm text-red-600">
              ({{ updatesSummary.security }} security)
            </span>
            <span v-if="updatesSummary.critical > 0" class="text-sm font-medium text-red-700">
              {{ updatesSummary.critical }} critical
            </span>
          </template>
          <template v-else-if="availableUpdates">
            <div class="flex items-center gap-2 text-success-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span class="font-medium">System up to date</span>
            </div>
          </template>
          <template v-else>
            <span class="text-sm text-gray-500">Click "Check for Updates" to scan</span>
          </template>
        </div>

        <!-- Update Actions -->
        <div class="flex items-center gap-2">
          <button
            @click="checkForUpdates"
            :disabled="isCheckingUpdates"
            class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg
              :class="['w-4 h-4', isCheckingUpdates ? 'animate-spin' : '']"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                v-if="isCheckingUpdates"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
              <path
                v-else
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            {{ isCheckingUpdates ? 'Checking...' : 'Check for Updates' }}
          </button>

          <button
            v-if="updatesSummary && updatesSummary.count > 0"
            @click="installUpdates"
            :disabled="isInstallingUpdates"
            class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg
              :class="['w-4 h-4', isInstallingUpdates ? 'animate-spin' : '']"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                v-if="isInstallingUpdates"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
              <path
                v-else
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            {{ isInstallingUpdates ? 'Installing...' : 'Install Updates' }}
          </button>
        </div>
      </div>

      <!-- Progress Bar -->
      <div v-if="isInstallingUpdates" class="mt-3">
        <div class="flex items-center gap-3">
          <div class="flex-1 bg-gray-200 rounded-full h-2">
            <div
              class="bg-primary-600 h-2 rounded-full transition-all duration-300"
              :style="{ width: `${updateProgress}%` }"
            ></div>
          </div>
          <span class="text-sm text-gray-600 w-12 text-right">{{ updateProgress }}%</span>
        </div>
      </div>

      <!-- Available Updates List -->
      <div
        v-if="availableUpdates && availableUpdates.updates.length > 0 && !isInstallingUpdates"
        class="mt-3 space-y-2"
      >
        <div class="flex items-center justify-between text-sm">
          <span class="font-medium text-gray-700">Available Updates:</span>
          <div class="flex gap-2">
            <button
              @click="selectAllUpdates"
              class="text-primary-600 hover:text-primary-700"
            >
              Select all
            </button>
            <span class="text-gray-300">|</span>
            <button
              @click="deselectAllUpdates"
              class="text-gray-500 hover:text-gray-700"
            >
              Clear
            </button>
          </div>
        </div>
        <div class="space-y-1">
          <label
            v-for="update in availableUpdates.updates"
            :key="update.id"
            class="flex items-center gap-3 p-2 rounded-md hover:bg-gray-100 cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="selectedUpdateIds.includes(update.id)"
              @change="toggleUpdateSelection(update.id)"
              class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-gray-900">v{{ update.version }}</span>
                <span :class="['px-2 py-0.5 text-xs font-medium rounded', getUpdateSeverityClass(update.severity)]">
                  {{ update.severity }}
                </span>
              </div>
              <p class="text-sm text-gray-600 truncate">{{ update.description }}</p>
            </div>
          </label>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="flex items-center gap-4 px-4 py-2 bg-gray-100 border-b border-gray-200">
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-600">Type:</label>
        <select
          v-model="eventTypeFilter"
          class="text-sm border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        >
          <option v-for="option in eventTypeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-600">Severity:</label>
        <select
          v-model="severityFilter"
          class="text-sm border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        >
          <option v-for="option in severityOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <div class="ml-auto text-sm text-gray-500">
        <span class="font-medium text-gray-700">{{ filteredEvents.length }}</span>
        event{{ filteredEvents.length === 1 ? '' : 's' }}
        <span v-if="totalEvents > events.length" class="text-gray-400">
          (showing {{ events.length }} of {{ totalEvents }})
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex-1 flex flex-col items-center justify-center py-12 text-gray-400">
      <svg class="w-8 h-8 animate-spin mb-3" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <span>Loading events...</span>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="filteredEvents.length === 0"
      class="flex-1 flex flex-col items-center justify-center py-12 text-gray-400"
    >
      <svg class="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p v-if="events.length === 0" class="text-center">
        No lifecycle events recorded yet.<br />
        <span class="text-sm">Events will appear here as they occur.</span>
      </p>
      <p v-else>No events match the current filters.</p>
    </div>

    <!-- Events Table -->
    <div v-else class="flex-1 overflow-y-auto">
      <table class="w-full">
        <thead class="bg-gray-50 sticky top-0">
          <tr>
            <th class="w-10 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider"></th>
            <th class="w-40 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Time</th>
            <th class="w-44 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Type</th>
            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Message</th>
            <th class="w-24 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Duration</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr
            v-for="event in filteredEvents"
            :key="event.id"
            :class="[
              'hover:bg-gray-50 transition-colors',
              event.severity === 'error' || event.severity === 'critical' ? 'bg-red-50/50' : '',
              event.severity === 'warning' ? 'bg-yellow-50/50' : '',
            ]"
          >
            <!-- Severity Icon -->
            <td class="px-4 py-3">
              <div
                :class="[
                  'w-7 h-7 rounded-full flex items-center justify-center',
                  getSeverityClasses(event.severity).bg,
                ]"
              >
                <svg
                  :class="['w-4 h-4', getSeverityClasses(event.severity).icon]"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    :d="getSeverityIcon(event.severity)"
                  />
                </svg>
              </div>
            </td>

            <!-- Time -->
            <td class="px-4 py-3">
              <div class="text-sm text-gray-900">{{ formatFullTime(event.timestamp) }}</div>
              <div class="text-xs text-gray-500">{{ formatRelativeTime(event.timestamp) }}</div>
            </td>

            <!-- Event Type -->
            <td class="px-4 py-3">
              <div class="inline-flex items-center gap-2 px-2 py-1 bg-gray-100 rounded text-sm font-medium text-gray-700">
                <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getEventIcon(event.event_type)" />
                </svg>
                {{ formatEventType(event.event_type) }}
              </div>
            </td>

            <!-- Message -->
            <td class="px-4 py-3">
              <div class="text-sm text-gray-900">{{ event.message }}</div>
              <div
                v-if="event.details && Object.keys(event.details).length > 0"
                class="flex flex-wrap gap-1 mt-1"
              >
                <span
                  v-for="(value, key) in event.details"
                  :key="key"
                  class="inline-flex px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                >
                  {{ formatDetailKey(String(key)) }}: {{ value }}
                </span>
              </div>
            </td>

            <!-- Duration -->
            <td class="px-4 py-3">
              <span v-if="event.duration_ms" class="text-sm font-mono text-gray-600">
                {{ formatDuration(event.duration_ms) }}
              </span>
              <span v-else class="text-gray-400">-</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Load More Button -->
      <div v-if="hasMore" class="flex justify-center py-3 border-t border-gray-100">
        <button
          @click="loadMoreEvents"
          :disabled="isLoadingMore"
          class="inline-flex items-center gap-2 px-4 py-2 text-sm text-primary-600 hover:text-primary-700 disabled:opacity-50"
        >
          <svg
            v-if="isLoadingMore"
            class="w-4 h-4 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          {{ isLoadingMore ? 'Loading...' : 'Load more events' }}
        </button>
      </div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between px-4 py-2 bg-gray-50 border-t border-gray-200">
      <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input
          type="checkbox"
          v-model="autoRefresh"
          class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
        />
        Auto-refresh (every {{ Math.round(autoRefreshInterval / 1000) }}s)
      </label>
      <span v-if="lastRefresh" class="text-xs text-gray-400">
        Last updated: {{ formatRelativeTime(lastRefresh) }}
      </span>
    </div>
  </div>
</template>
