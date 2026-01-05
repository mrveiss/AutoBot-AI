// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Command Approval Composable
 *
 * Handles command approval logic for the chat interface including:
 * - Approve/deny commands
 * - Poll command execution state
 * - Comment functionality
 * - Auto-approve settings
 * - Remember approval for project (Permission v2)
 *
 * Issue #184: Extracted from ChatMessages.vue for better maintainability
 * Issue: Permission System v2 - Claude Code Style
 */

import { ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/debugUtils'
import { useChatStore } from '@/stores/useChatStore'
import { usePermissionStore } from '@/stores/usePermissionStore'

const logger = createLogger('useCommandApproval')

export interface CommandApprovalState {
  processingApproval: boolean
  showCommentInput: boolean
  activeCommentSessionId: string | null
  approvalComment: string
  pendingApprovalDecision: boolean | null
  autoApproveFuture: boolean
  rememberForProject: boolean // Permission v2: Remember approval for this project
  currentProjectPath: string | null // Permission v2: Current project path
}

export interface CommandResult {
  state: 'completed' | 'failed' | 'denied' | 'timeout' | 'error'
  output?: string
  stderr?: string
  return_code?: number
  command?: string
  error?: string
}

export function useCommandApproval() {
  const { showToast } = useToast()
  const chatStore = useChatStore()
  const permissionStore = usePermissionStore()

  // State
  const processingApproval = ref(false)
  const showCommentInput = ref(false)
  const activeCommentSessionId = ref<string | null>(null)
  const approvalComment = ref('')
  const pendingApprovalDecision = ref<boolean | null>(null)
  const autoApproveFuture = ref(false)

  // Permission v2: Remember for project state
  const rememberForProject = ref(false)
  const currentProjectPath = ref<string | null>(null)
  const currentUserId = ref<string>('web_user')

  // Helper notification
  const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    showToast(message, type, type === 'error' ? 5000 : 3000)
  }

  /**
   * Set the current project path for approval memory
   * Permission v2: Called when project context changes
   */
  const setProjectContext = (projectPath: string | null, userId?: string) => {
    currentProjectPath.value = projectPath
    if (userId) {
      currentUserId.value = userId
    }
    logger.debug('Project context set:', { projectPath, userId })
  }

  /**
   * Poll command state from queue (event-driven, no timeouts!)
   */
  const pollCommandState = async (
    command_id: string,
    callback: (result: CommandResult) => void
  ) => {
    const maxAttempts = 100 // 100 * 500ms = 50 seconds max
    let attempt = 0

    const poll = async () => {
      try {
        const backendUrl = await appConfig.getApiUrl(
          `/api/agent-terminal/commands/${command_id}`
        )
        const response = await fetch(backendUrl)

        if (!response.ok) {
          logger.error('Failed to get command state:', response.status)
          if (attempt < maxAttempts) {
            attempt++
            setTimeout(poll, 500)
          } else {
            callback({ state: 'error', error: 'HTTP error' })
          }
          return
        }

        const command = await response.json()
        logger.debug(`Command state (attempt ${attempt + 1}):`, command.state)

        // Check if command is finished
        if (
          command.state === 'completed' ||
          command.state === 'failed' ||
          command.state === 'denied'
        ) {
          logger.debug('Command finished:', {
            state: command.state,
            output_length: command.output?.length || 0,
            return_code: command.return_code
          })
          callback({
            state: command.state,
            output: command.output,
            stderr: command.stderr,
            return_code: command.return_code,
            command: command.command
          })
          return // Stop polling
        }

        // Command still running - poll again
        if (attempt < maxAttempts) {
          attempt++
          setTimeout(poll, 500) // Poll every 500ms
        } else {
          logger.error('Polling timed out after 50 seconds')
          callback({ state: 'timeout', error: 'Polling timeout' })
        }
      } catch (error) {
        logger.error('Polling error:', error)
        if (attempt < maxAttempts) {
          attempt++
          setTimeout(poll, 500)
        } else {
          callback({ state: 'error', error: (error as Error).message })
        }
      }
    }

    // Start polling
    logger.debug('Starting command state polling for:', command_id)
    poll()
  }

  /**
   * Approve or deny a command via HTTP POST to agent-terminal API
   *
   * Permission v2: If rememberForProject is true and user approves,
   * stores the approval in project memory for future auto-approval.
   */
  const approveCommand = async (
    terminal_session_id: string,
    approved: boolean,
    comment?: string,
    command_id?: string,
    onMessageUpdate?: (sessionId: string, status: string, comment?: string) => void,
    commandInfo?: { command: string; risk_level: string } // Permission v2: Command details for memory
  ) => {
    if (!terminal_session_id) {
      logger.error('No terminal_session_id provided for approval')
      return
    }

    processingApproval.value = true
    logger.debug(
      `${approved ? 'Approving' : 'Denying'} command for session:`,
      terminal_session_id
    )
    if (comment) {
      logger.debug('With comment:', comment)
    }
    if (autoApproveFuture.value) {
      logger.debug('Auto-approve similar commands in future:', autoApproveFuture.value)
    }
    if (rememberForProject.value) {
      logger.debug('Remember for project:', currentProjectPath.value)
    }

    try {
      // Get backend URL from appConfig
      const backendUrl = await appConfig.getApiUrl(
        `/api/agent-terminal/sessions/${terminal_session_id}/approve`
      )

      const response = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          approved,
          user_id: currentUserId.value,
          comment: comment || null,
          auto_approve_future: autoApproveFuture.value, // Send auto-approve preference
          remember_for_project: rememberForProject.value, // Permission v2
          project_path: currentProjectPath.value // Permission v2
        })
      })

      const result = await response.json()
      logger.debug('Approval response:', result)

      if (result.status === 'approved' || result.status === 'denied') {
        logger.debug(`Command ${approved ? 'approved' : 'denied'} successfully`)
        notify(`Command ${approved ? 'approved' : 'denied'}`, approved ? 'success' : 'warning')

        // Callback to update message metadata
        if (onMessageUpdate) {
          onMessageUpdate(terminal_session_id, result.status, comment || result.comment)
        }

        // START POLLING: If approved and we have command_id, poll for completion
        if (result.status === 'approved' && approved && command_id) {
          logger.debug('Starting polling for approved command:', command_id)

          pollCommandState(command_id, pollResult => {
            logger.debug('Command execution complete:', pollResult)

            if (pollResult.state === 'completed') {
              logger.debug('Command completed successfully')
              logger.debug('Output:', pollResult.output)
              // Note: Backend already handles LLM interpretation and sends it to chat
              // The output will appear naturally through the WebSocket/streaming flow
            } else if (pollResult.state === 'failed') {
              logger.error('Command failed:', pollResult.stderr)
              notify('Command execution failed', 'error')
            } else if (pollResult.state === 'timeout') {
              logger.warn('Polling timed out')
              notify('Command execution timed out', 'warning')
            } else if (pollResult.state === 'error') {
              logger.error('Polling error:', pollResult.error)
              notify('Command polling error', 'error')
            }
          })
        } else if (!command_id && approved) {
          logger.warn('No command_id available for polling (legacy approval flow)')
        }

        // Permission v2: Store approval in project memory if requested
        if (
          rememberForProject.value &&
          approved &&
          currentProjectPath.value &&
          commandInfo &&
          permissionStore.isEnabled
        ) {
          const stored = await permissionStore.storeApproval(
            currentProjectPath.value,
            currentUserId.value,
            commandInfo.command,
            commandInfo.risk_level,
            'Bash',
            comment
          )
          if (stored) {
            logger.info('Approval stored in project memory')
            notify('Approval remembered for this project', 'info')
          }
        }

        // Reset checkboxes after submission
        autoApproveFuture.value = false
        rememberForProject.value = false
        // Issue #680: Clear pending approval flag to allow polling to resume
        chatStore.setPendingApproval(false)
      } else if (result.status === 'error') {
        logger.error('Approval error:', result.error)
        notify(`Approval failed: ${result.error}`, 'error')
        // Issue #680: Clear pending approval flag on error too
        chatStore.setPendingApproval(false)
      }

      processingApproval.value = false
    } catch (error) {
      logger.error('Error sending approval:', error)
      notify('Failed to process command approval', 'error')
      processingApproval.value = false
      // Issue #680: Clear pending approval flag on exception
      chatStore.setPendingApproval(false)
    }
  }

  /**
   * Prompt user for a comment before approving/denying
   */
  const promptForComment = (sessionId: string) => {
    showCommentInput.value = true
    activeCommentSessionId.value = sessionId
    approvalComment.value = ''
    pendingApprovalDecision.value = null
  }

  /**
   * Submit approval with a comment
   */
  const submitApprovalWithComment = async (
    sessionId: string,
    approved: boolean | null,
    command_id?: string,
    onMessageUpdate?: (sessionId: string, status: string, comment?: string) => void
  ) => {
    if (!approvalComment.value.trim()) {
      logger.warn('Cannot submit approval with empty comment')
      return
    }

    // Determine approval decision
    const finalDecision = approved !== null ? approved : pendingApprovalDecision.value

    if (finalDecision === null) {
      logger.error('No approval decision provided')
      return
    }

    // Call existing approveCommand with comment
    await approveCommand(
      sessionId,
      finalDecision,
      approvalComment.value,
      command_id,
      onMessageUpdate
    )

    // Reset state
    cancelComment()
  }

  /**
   * Cancel comment input
   */
  const cancelComment = () => {
    showCommentInput.value = false
    activeCommentSessionId.value = null
    approvalComment.value = ''
    pendingApprovalDecision.value = null
  }

  /**
   * Get risk level CSS class
   */
  const getRiskClass = (riskLevel: string): string => {
    const riskClasses: Record<string, string> = {
      LOW: 'text-green-600',
      MODERATE: 'text-yellow-600',
      HIGH: 'text-orange-600',
      DANGEROUS: 'text-red-600'
    }
    return riskClasses[riskLevel] || 'text-gray-600'
  }

  return {
    // State
    processingApproval,
    showCommentInput,
    activeCommentSessionId,
    approvalComment,
    pendingApprovalDecision,
    autoApproveFuture,

    // Permission v2: Project memory state
    rememberForProject,
    currentProjectPath,

    // Methods
    approveCommand,
    pollCommandState,
    promptForComment,
    submitApprovalWithComment,
    cancelComment,
    getRiskClass,

    // Permission v2: Project context methods
    setProjectContext
  }
}
