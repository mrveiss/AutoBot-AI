// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Permission Store - Claude Code Style Permission System
 *
 * Manages permission system state including:
 * - Current permission mode
 * - Permission rules (allow/ask/deny)
 * - Project approval memory
 *
 * Issue: Permission System v2 - Claude Code Style
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePermissionStore')

// Permission modes matching backend PermissionMode enum
export type PermissionMode =
  | 'default'
  | 'acceptEdits'
  | 'plan'
  | 'dontAsk'
  | 'bypassPermissions'

// Permission actions matching backend PermissionAction enum
export type PermissionAction = 'allow' | 'ask' | 'deny'

// Permission rule interface
export interface PermissionRule {
  tool: string
  pattern: string
  action: PermissionAction
  description: string
}

// Approval record interface
export interface ApprovalRecord {
  pattern: string
  tool: string
  risk_level: string
  user_id: string
  created_at: number
  original_command: string
  comment?: string
}

// Permission status interface
export interface PermissionStatus {
  enabled: boolean
  mode: PermissionMode
  approval_memory_enabled: boolean
  approval_memory_ttl_days: number
  rules_file: string
  rules_count: {
    allow: number
    ask: number
    deny: number
    total: number
  }
}

// API response types
interface PermissionModeResponse {
  mode: string
  enabled: boolean
  is_admin_only: boolean
  allowed_modes: string[]
}

interface PermissionRulesResponse {
  allow: PermissionRule[]
  ask: PermissionRule[]
  deny: PermissionRule[]
}

interface ProjectApprovalsResponse {
  project_path: string
  approvals: ApprovalRecord[]
}

export const usePermissionStore = defineStore('permission', () => {
  // Issue #820: AbortController for cancelling in-flight fetch requests
  let abortController: AbortController | null = null

  function getSignal(): AbortSignal {
    if (!abortController) {
      abortController = new AbortController()
    }
    return abortController.signal
  }

  function abortPendingRequests(): void {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  // State
  const status = ref<PermissionStatus | null>(null)
  const currentMode = ref<PermissionMode>('default')
  const allowedModes = ref<PermissionMode[]>(['default', 'acceptEdits', 'plan'])
  const isAdminOnly = ref(false)
  const enabled = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Rules state
  const allowRules = ref<PermissionRule[]>([])
  const askRules = ref<PermissionRule[]>([])
  const denyRules = ref<PermissionRule[]>([])

  // Project approvals state
  const projectApprovals = ref<Map<string, ApprovalRecord[]>>(new Map())
  const currentProjectPath = ref<string | null>(null)

  // Computed
  const isEnabled = computed(() => enabled.value)
  const totalRulesCount = computed(
    () => allowRules.value.length + askRules.value.length + denyRules.value.length
  )

  // Getters
  const getAllRules = computed(() => ({
    allow: allowRules.value,
    ask: askRules.value,
    deny: denyRules.value
  }))

  const getCurrentProjectApprovals = computed(() => {
    if (!currentProjectPath.value) return []
    return projectApprovals.value.get(currentProjectPath.value) || []
  })

  // Actions

  /**
   * Fetch permission system status
   */
  async function fetchStatus(): Promise<PermissionStatus | null> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl('/api/permissions/status')
      const response = await fetch(url, { signal: getSignal() })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const data: PermissionStatus = await response.json()
      status.value = data
      enabled.value = data.enabled
      currentMode.value = data.mode as PermissionMode

      logger.debug('Permission status fetched:', data)
      return data
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return null
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch permission status:', msg)
      error.value = msg
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch current permission mode
   */
  async function fetchMode(isAdmin = false): Promise<void> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl(`/api/permissions/mode?is_admin=${isAdmin}`)
      const response = await fetch(url, { signal: getSignal() })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const data: PermissionModeResponse = await response.json()
      currentMode.value = data.mode as PermissionMode
      enabled.value = data.enabled
      isAdminOnly.value = data.is_admin_only
      allowedModes.value = data.allowed_modes as PermissionMode[]

      logger.debug('Permission mode fetched:', data)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch permission mode:', msg)
      error.value = msg
    } finally {
      loading.value = false
    }
  }

  /**
   * Set permission mode
   */
  async function setMode(mode: PermissionMode, isAdmin = false): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl(`/api/permissions/mode?is_admin=${isAdmin}`)
      const response = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error: ${response.status}`)
      }

      const data: PermissionModeResponse = await response.json()
      currentMode.value = data.mode as PermissionMode
      isAdminOnly.value = data.is_admin_only
      allowedModes.value = data.allowed_modes as PermissionMode[]

      logger.info('Permission mode set to:', mode)
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to set permission mode:', msg)
      error.value = msg
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch all permission rules
   */
  async function fetchRules(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl('/api/permissions/rules')
      const response = await fetch(url, { signal: getSignal() })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const data: PermissionRulesResponse = await response.json()
      allowRules.value = data.allow
      askRules.value = data.ask
      denyRules.value = data.deny

      logger.debug('Permission rules fetched:', {
        allow: data.allow.length,
        ask: data.ask.length,
        deny: data.deny.length
      })
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch permission rules:', msg)
      error.value = msg
    } finally {
      loading.value = false
    }
  }

  /**
   * Add a new permission rule
   */
  async function addRule(
    tool: string,
    pattern: string,
    action: PermissionAction,
    description = '',
    isAdmin = false
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl(`/api/permissions/rules?is_admin=${isAdmin}`)
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, pattern, action, description })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error: ${response.status}`)
      }

      // Refresh rules after adding
      await fetchRules()

      logger.info('Permission rule added:', { tool, pattern, action })
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to add permission rule:', msg)
      error.value = msg
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Remove a permission rule
   */
  async function removeRule(tool: string, pattern: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const url = await appConfig.getApiUrl('/api/permissions/rules')
      const response = await fetch(url, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, pattern })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error: ${response.status}`)
      }

      // Refresh rules after removing
      await fetchRules()

      logger.info('Permission rule removed:', { tool, pattern })
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to remove permission rule:', msg)
      error.value = msg
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Check what action would be taken for a command
   */
  async function checkCommand(
    command: string,
    tool = 'Bash',
    isAdmin = false
  ): Promise<{ result: string; pattern?: string; description?: string } | null> {
    try {
      const url = await appConfig.getApiUrl(`/api/permissions/check?is_admin=${isAdmin}`)
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, tool })
      })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      return await response.json()
    } catch (e) {
      logger.error('Failed to check command:', e)
      return null
    }
  }

  /**
   * Fetch project approvals
   */
  async function fetchProjectApprovals(
    projectPath: string,
    userId: string
  ): Promise<ApprovalRecord[]> {
    loading.value = true
    error.value = null

    try {
      const encodedPath = encodeURIComponent(projectPath)
      const url = await appConfig.getApiUrl(
        `/api/permissions/memory/${encodedPath}?user_id=${userId}`
      )
      const response = await fetch(url)

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const data: ProjectApprovalsResponse = await response.json()
      projectApprovals.value.set(projectPath, data.approvals)
      currentProjectPath.value = projectPath

      logger.debug('Project approvals fetched:', {
        project: projectPath,
        count: data.approvals.length
      })
      return data.approvals
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch project approvals:', msg)
      error.value = msg
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Store an approval in memory
   */
  async function storeApproval(
    projectPath: string,
    userId: string,
    command: string,
    riskLevel: string,
    tool = 'Bash',
    comment?: string
  ): Promise<boolean> {
    try {
      const params = new URLSearchParams({
        project_path: projectPath,
        user_id: userId,
        command,
        risk_level: riskLevel,
        tool
      })
      if (comment) {
        params.append('comment', comment)
      }

      const url = await appConfig.getApiUrl(`/api/permissions/memory?${params.toString()}`)
      const response = await fetch(url, { method: 'POST' })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      logger.info('Approval stored:', { projectPath, command, riskLevel })
      return true
    } catch (e) {
      logger.error('Failed to store approval:', e)
      return false
    }
  }

  /**
   * Clear project approvals
   */
  async function clearProjectApprovals(
    projectPath: string,
    userId?: string
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const encodedPath = encodeURIComponent(projectPath)
      let url = await appConfig.getApiUrl(`/api/permissions/memory/${encodedPath}`)
      if (userId) {
        url += `?user_id=${userId}`
      }

      const response = await fetch(url, { method: 'DELETE' })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      // Clear from local state
      projectApprovals.value.delete(projectPath)

      logger.info('Project approvals cleared:', { projectPath, userId })
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to clear project approvals:', msg)
      error.value = msg
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Initialize store - fetch status and rules.
   * Aborts any pending requests from previous initialization (#820).
   */
  async function initialize(isAdmin = false): Promise<void> {
    abortPendingRequests()
    await fetchStatus()
    if (enabled.value) {
      await Promise.all([fetchMode(isAdmin), fetchRules()])
    }
  }

  return {
    // State
    status,
    currentMode,
    allowedModes,
    isAdminOnly,
    enabled,
    loading,
    error,
    allowRules,
    askRules,
    denyRules,
    projectApprovals,
    currentProjectPath,

    // Computed
    isEnabled,
    totalRulesCount,
    getAllRules,
    getCurrentProjectApprovals,

    // Actions
    fetchStatus,
    fetchMode,
    setMode,
    fetchRules,
    addRule,
    removeRule,
    checkCommand,
    fetchProjectApprovals,
    storeApproval,
    clearProjectApprovals,
    initialize,
    abortPendingRequests
  }
})
