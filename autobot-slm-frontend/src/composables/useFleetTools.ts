// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The fleet diagnostic tools ToolsView and FleetToolsTab both offer (#15665).
 *
 * FleetToolsTab was extracted from ToolsView by copying its script. Once both
 * rendered the same i18n keys the two copies were token-identical and the SLM
 * duplication gate failed -- the copy was the defect; the shared keys only made
 * it visible. One implementation here; each view adds only what it alone offers.
 */

import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFleetStore } from '@/stores/fleet'
import { slmApiClient } from '@/utils/ApiClient'
import { REMOTE_EXEC_TIMEOUT_MS } from '@/constants/api-timeouts'

/** What `POST /nodes/{id}/exec` returns. */
interface ExecResult {
  output?: string
  stdout?: string
  stderr?: string
}

export function useFleetTools() {
  const { t } = useI18n()
  const fleetStore = useFleetStore()

  const activeTool = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const result = ref<string | null>(null)

  // Tool-specific state
  const selectedNode = ref<string>('')
  const selectedService = ref<string>('')
  const redisCommand = ref<string>('PING')
  const shellCommand = ref<string>('uptime')
  const logLines = ref<number>(100)

  // Available nodes, and the one selected
  const nodes = computed(() => fleetStore.nodeList)
  const selectedNodeDetails = computed(() => {
    if (!selectedNode.value) return null
    return nodes.value.find((n) => n.node_id === selectedNode.value) || null
  })

  function resetOutput(): void {
    error.value = null
    result.value = null
  }

  function selectTool(toolId: string): void {
    activeTool.value = toolId
    resetOutput()
  }

  function closeTool(): void {
    activeTool.value = null
    resetOutput()
  }

  /** Show `messageKey` and refuse the run when `ok` is false. */
  function requireInput(ok: boolean, messageKey: string): boolean {
    if (!ok) error.value = t(messageKey)
    return ok
  }

  /**
   * Run one tool action: clear the last output, show progress, and put either
   * the result or the failure on screen. `fallbackKey` is the message for a
   * failure that carries none of its own.
   */
  async function runTool(task: () => Promise<string>, fallbackKey: string): Promise<void> {
    loading.value = true
    resetOutput()
    try {
      result.value = await task()
    } catch (e) {
      error.value = e instanceof Error ? e.message : t(fallbackKey)
    } finally {
      loading.value = false
    }
  }

  /**
   * Run a command on a node over SSH.
   *
   * `rawRequest` keeps the `err.detail` body these panels render; the client adds
   * the base URL, the bearer, the 401 handler and the timeout. `getAuthHeaders()`
   * returned `{}` whenever the store's `token` ref was null, and that ref was
   * seeded from storage once at store construction -- so a token that landed
   * later left the command dispatched with no credential. `/exec` runs over SSH,
   * so it takes the long remote-exec budget, not the 30s default (#13140).
   */
  async function exec(nodeId: string, command: string, failureKey: string): Promise<ExecResult> {
    const response = await slmApiClient.rawRequest(`/nodes/${nodeId}/exec`, {
      method: 'POST',
      timeout: REMOTE_EXEC_TIMEOUT_MS,
      body: { command },
    })
    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || t(failureKey))
    }
    return response.json()
  }

  async function runRedisCommand(): Promise<void> {
    if (!requireInput(!!redisCommand.value.trim(), 'toolsView.pleaseEnterARedis')) return
    await runTool(async () => {
      // Use the Redis node if available, otherwise the selected node
      const redisNode = nodes.value.find((n) => n.roles?.includes('redis'))
      const targetNode = redisNode || (selectedNode.value ? selectedNodeDetails.value : null)
      if (!targetNode) throw new Error(t('toolsView.runNoNodeSelected'))
      const data = await exec(targetNode.node_id, `redis-cli ${redisCommand.value}`, 'toolsView.redisCommandFailed')
      return t('toolsView.redisResponse', { output: data.output || data.stdout || t('toolsView.noOutput') })
    }, 'toolsView.redisCommandFailed')
  }

  async function runShellCommand(): Promise<void> {
    if (!requireInput(!!selectedNode.value && !!shellCommand.value.trim(), 'toolsView.pleaseSelectANodeAnd')) return
    await runTool(async () => {
      const data = await exec(selectedNode.value, shellCommand.value, 'toolsView.commandExecutionFailed')
      return t('toolsView.commandOutputResult', {
        output: data.output || data.stdout || t('toolsView.noOutput'),
        stderr: data.stderr ? `Stderr:\n${data.stderr}` : '',
      })
    }, 'toolsView.commandExecutionFailed')
  }

  return {
    activeTool,
    loading,
    error,
    result,
    selectedNode,
    selectedService,
    redisCommand,
    shellCommand,
    logLines,
    nodes,
    selectedNodeDetails,
    selectTool,
    closeTool,
    requireInput,
    runTool,
    runRedisCommand,
    runShellCommand,
  }
}
