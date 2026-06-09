// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useOverseerAgent Composable
 *
 * Manages the Overseer Agent WebSocket connection for:
 * - Task decomposition and planning
 * - Step-by-step execution with streaming output
 * - Automatic command and output explanations
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { ref, computed, onScopeDispose, getCurrentScope } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl, getApiBase } from '@/config/ssot-config'
import { useWebSocket } from '@/composables/useWebSocket'

const logger = createLogger('useOverseerAgent')

// Types for overseer messages
export interface CommandBreakdownPart {
  part: string
  explanation: string
}

export interface CommandExplanation {
  summary: string
  breakdown: CommandBreakdownPart[]
  security_notes?: string | null
}

export interface OutputExplanation {
  summary: string
  key_findings: string[]
  details?: string | null
  next_steps?: string[] | null
}

export interface OverseerStep {
  step_number: number
  total_steps: number
  description: string
  command?: string | null
  status: 'pending' | 'running' | 'streaming' | 'explaining' | 'completed' | 'failed'
  command_explanation?: CommandExplanation | null
  output?: string
  output_explanation?: OutputExplanation | null
  return_code?: number | null
  execution_time?: number
  error?: string | null
  is_streaming?: boolean
  stream_complete?: boolean
}

export interface OverseerPlan {
  plan_id: string
  analysis: string
  steps: Array<{
    step_number: number
    description: string
    command?: string | null
  }>
}

export interface OverseerPlanContent {
  analysis?: string
  steps?: Array<{
    step_number: number
    description: string
    command?: string | null
  }>
  command?: string | null
  [key: string]: unknown
}

export interface OverseerUpdate {
  update_type: 'plan' | 'step_start' | 'stream' | 'step_complete' | 'error' | 'status'
  plan_id?: string
  task_id?: string
  step_number?: number
  total_steps?: number
  status?: string
  content?: OverseerPlanContent | StreamChunk | string
  timestamp?: string
}

export interface StreamChunk {
  task_id: string
  step_number: number
  chunk_type: 'stdout' | 'stderr' | 'command_explanation' | 'return_code' | 'error'
  content: string
  timestamp: string
  is_final: boolean
}

export interface UseOverseerAgentOptions {
  sessionId: string
  autoConnect?: boolean
  onPlanCreated?: (plan: OverseerPlan) => void
  onStepUpdate?: (step: OverseerStep) => void
  onStreamChunk?: (chunk: StreamChunk) => void
  onError?: (error: string) => void
  onComplete?: () => void
}

export function useOverseerAgent(options: UseOverseerAgentOptions) {
  const {
    sessionId,
    autoConnect = true,
    onPlanCreated,
    onStepUpdate,
    onStreamChunk,
    onError,
    onComplete
  } = options

  // State
  const isProcessing = ref(false)
  const currentPlan = ref<OverseerPlan | null>(null)
  const steps = ref<OverseerStep[]>([])
  const currentStep = ref<number>(0)
  const status = ref<string>('idle')
  const error = ref<string | null>(null)
  const streamingOutput = ref<Map<number, string>>(new Map())

  // Build the overseer WebSocket URL
  const getWebSocketUrl = (): string => {
    const backendUrl = getBackendUrl()
    const wsUrl = backendUrl.replace(/^http/, 'ws')
    return `${wsUrl}${getApiBase()}/overseer/ws/${sessionId}`
  }

  // WebSocket managed via useWebSocket composable
  const {
    isConnected,
    send: wsSend,
    connect,
    disconnect: wsDisconnect,
  } = useWebSocket(getWebSocketUrl(), {
    autoConnect: false,
    autoReconnect: true,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    maxReconnectDelay: 10000,
    parseJSON: false,
    onOpen: () => {
      error.value = null
      logger.info('Connected to overseer WebSocket')
    },
    onClose: (event) => {
      logger.info('Overseer WebSocket closed:', { code: event.code, reason: event.reason })
    },
    onError: (event) => {
      logger.error('Overseer WebSocket error:', event)
      error.value = 'WebSocket connection error'
      onError?.('WebSocket connection error')
    },
    onMessage: (data: unknown) => {
      if (typeof data === 'string') handleMessage(data)
    },
  })

  /**
   * Disconnect from WebSocket
   */
  const disconnect = (): void => {
    wsDisconnect()
    isProcessing.value = false
  }

  /**
   * Handle incoming WebSocket message
   */
  const handleMessage = (data: string): void => {
    try {
      const update: OverseerUpdate = JSON.parse(data)
      logger.debug('Received overseer update:', update.update_type)

      switch (update.update_type) {
        case 'plan':
          handlePlanUpdate(update)
          break
        case 'step_start':
          handleStepStart(update)
          break
        case 'stream':
          handleStreamUpdate(update)
          break
        case 'step_complete':
          handleStepComplete(update)
          break
        case 'error':
          handleError(update)
          break
        case 'status':
          handleStatus(update)
          break
        default:
          logger.warn('Unknown update type:', update.update_type)
      }
    } catch (e) {
      logger.error('Failed to parse overseer message:', e)
    }
  }

  /**
   * Handle plan creation update
   */
  const handlePlanUpdate = (update: OverseerUpdate): void => {
    const content = typeof update.content === 'object' && update.content !== null && !('chunk_type' in update.content)
      ? update.content as OverseerPlanContent
      : undefined
    currentPlan.value = {
      plan_id: update.plan_id || '',
      analysis: content?.analysis || '',
      steps: content?.steps || []
    }

    // Initialize steps array
    steps.value = (content?.steps || []).map((s) => ({
      step_number: s.step_number,
      total_steps: update.total_steps || content?.steps?.length || 0,
      description: s.description,
      command: s.command,
      status: 'pending' as const,
      output: ''
    }))

    status.value = 'planning'
    onPlanCreated?.(currentPlan.value)
  }

  /**
   * Handle step start update
   */
  const handleStepStart = (update: OverseerUpdate): void => {
    const stepNumber = update.step_number || 0
    currentStep.value = stepNumber
    status.value = 'executing'

    // #7275: content is `string | OverseerPlanContent | StreamChunk`; for step-start
    // events it carries StreamChunk-like fields. Cast at boundary; type-narrow guards
    // would be cleaner but add 4x lines for the same runtime behavior.
    const content = update.content as Record<string, any> | undefined

    // Update step status
    const step = steps.value.find(s => s.step_number === stepNumber)
    if (step) {
      step.status = 'running'
      step.command = content?.command
      onStepUpdate?.(step)
    }
  }

  /**
   * Handle streaming output update
   */
  const handleStreamUpdate = (update: OverseerUpdate): void => {
    const stepNumber = update.step_number || 0
    const chunk = update.content as StreamChunk

    // Accumulate streaming output
    const currentOutput = streamingOutput.value.get(stepNumber) || ''
    if (chunk?.chunk_type === 'stdout' || chunk?.chunk_type === 'stderr') {
      streamingOutput.value.set(stepNumber, currentOutput + chunk.content)
    }

    // Update step with streaming output
    const step = steps.value.find(s => s.step_number === stepNumber)
    if (step) {
      step.status = 'streaming'
      step.output = streamingOutput.value.get(stepNumber) || ''
      step.is_streaming = true
      onStepUpdate?.(step)
    }

    onStreamChunk?.(chunk)
  }

  /**
   * Handle step completion update
   */
  const handleStepComplete = (update: OverseerUpdate): void => {
    const stepNumber = update.step_number || 0
    // #7275: same boundary cast as handleStepStart (see note above)
    const content = update.content as Record<string, any> | undefined

    // Update step with final results
    const step = steps.value.find(s => s.step_number === stepNumber)
    if (step) {
      step.status = content?.status === 'completed' ? 'completed' : 'failed'
      step.command = content?.command
      step.command_explanation = content?.command_explanation
      step.output = content?.output || streamingOutput.value.get(stepNumber) || ''
      step.output_explanation = content?.output_explanation
      step.return_code = content?.return_code
      step.execution_time = content?.execution_time
      step.error = content?.error
      step.is_streaming = false
      step.stream_complete = true

      onStepUpdate?.(step)
    }

    // Clear streaming buffer for this step
    streamingOutput.value.delete(stepNumber)

    // Check if all steps complete
    const allComplete = steps.value.every(s =>
      s.status === 'completed' || s.status === 'failed'
    )
    if (allComplete) {
      isProcessing.value = false
      status.value = 'complete'
      onComplete?.()
    }
  }

  /**
   * Handle error update
   */
  const handleError = (update: OverseerUpdate): void => {
    // #7275: content union narrowed at boundary (same pattern as other handlers)
    const content = update.content as Record<string, any> | undefined
    const errorMsg = content?.error || 'Unknown error'
    error.value = errorMsg
    status.value = 'error'
    isProcessing.value = false
    onError?.(errorMsg)
  }

  /**
   * Handle status update
   */
  const handleStatus = (update: OverseerUpdate): void => {
    if (update.status === 'complete') {
      isProcessing.value = false
      status.value = 'complete'
      onComplete?.()
    } else if (update.status === 'cancelled') {
      isProcessing.value = false
      status.value = 'cancelled'
    }
  }

  /**
   * Submit a query to the overseer
   */
  const submitQuery = (query: string, context?: Record<string, any>): void => {
    if (!isConnected.value) {
      error.value = 'Not connected to overseer'
      onError?.('Not connected to overseer')
      return
    }

    // Reset state
    currentPlan.value = null
    steps.value = []
    currentStep.value = 0
    error.value = null
    streamingOutput.value.clear()
    isProcessing.value = true
    status.value = 'planning'

    // Send query
    wsSend({
      type: 'query',
      query,
      context
    })

    logger.info('Submitted query to overseer:', query.substring(0, 100))
  }

  /**
   * Cancel current execution
   */
  const cancel = (): void => {
    wsSend({ type: 'cancel' })
    isProcessing.value = false
    status.value = 'cancelled'
  }

  /**
   * Get status
   */
  const getStatus = (): void => {
    wsSend({ type: 'status' })
  }

  // Computed
  const progressPercentage = computed(() => {
    if (steps.value.length === 0) return 0
    const completed = steps.value.filter(s =>
      s.status === 'completed' || s.status === 'failed'
    ).length
    return Math.round((completed / steps.value.length) * 100)
  })

  const currentStepData = computed(() => {
    return steps.value.find(s => s.step_number === currentStep.value) || null
  })

  // Auto-connect if enabled
  if (autoConnect) {
    connect()
  }

  // useWebSocket registers scope-dispose cleanup automatically;
  // we also reset isProcessing on unmount/scope disposal
  if (getCurrentScope()) {
    onScopeDispose(() => {
      isProcessing.value = false
    })
  }

  return {
    // State
    isConnected,
    isProcessing,
    currentPlan,
    steps,
    currentStep,
    currentStepData,
    status,
    error,
    progressPercentage,

    // Methods
    connect,
    disconnect,
    submitQuery,
    cancel,
    getStatus
  }
}
