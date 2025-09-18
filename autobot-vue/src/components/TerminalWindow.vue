<template>
  <div class="terminal-window-standalone" data-testid="terminal-window">
    <!-- Terminal Header -->
    <TerminalHeader
      :session-title="sessionTitle"
      :has-running-processes="hasRunningProcesses"
      :automation-paused="automationPaused"
      :has-automated-workflow="hasAutomatedWorkflow"
      :has-active-process="hasActiveProcess"
      :connecting="connecting"
      @emergency-kill="emergencyKillAll"
      @toggle-automation="workflowAutomation.toggleAutomationPause"
      @interrupt-process="interruptProcess"
      @reconnect="reconnect"
      @clear-terminal="clearTerminal"
      @close-window="closeWindow"
    />

    <!-- Terminal Status Bar -->
    <TerminalStatusBar
      :connection-status="connectionStatus"
      :connecting="connecting"
      :can-input="canInput"
      :session-id="sessionId"
      :output-lines-count="outputLines.length"
    />

    <!-- Terminal Main Area -->
    <div class="terminal-main" ref="terminalMain">
      <!-- Terminal Output -->
      <TerminalOutput
        :output-lines="outputLines"
        @focus-input="focusInput"
        ref="terminalOutputComponent"
      />

      <!-- Terminal Input -->
      <TerminalInput
        v-model:current-input="currentInput"
        :current-prompt="currentPrompt"
        :can-input="canInput"
        :show-cursor="showCursor"
        :has-automated-workflow="hasAutomatedWorkflow"
        :command-history="commandHistory"
        @send-command="sendCommand"
        @history-navigation="handleHistoryNavigation"
        @interrupt-signal="interruptProcess"
        @exit-signal="sendExitSignal"
        @clear-terminal="clearTerminal"
        @start-example-workflow="workflowAutomation.startExampleWorkflow"
        @download-log="downloadLog"
        @share-session="shareSession"
        ref="terminalInputComponent"
      />
    </div>

    <!-- Terminal Modals -->
    <TerminalModals
      :show-reconnect-modal="showReconnectModal"
      :show-command-confirmation="showCommandConfirmation"
      :show-kill-confirmation="showKillConfirmation"
      :show-legacy-modal="showLegacyModal"
      :pending-command="pendingCommand"
      :pending-command-risk="pendingCommandRisk"
      :pending-command-reasons="pendingCommandReasons"
      :running-processes="runningProcesses"
      :pending-workflow-step="pendingWorkflowStep"
      @hide-reconnect-modal="hideReconnectModal"
      @reconnect="reconnect"
      @cancel-command="cancelCommand"
      @execute-confirmed-command="executeConfirmedCommand"
      @cancel-kill="showKillConfirmation = false"
      @confirm-emergency-kill="confirmEmergencyKill"
      @confirm-workflow-step="workflowAutomation.confirmWorkflowStep"
      @skip-workflow-step="workflowAutomation.skipWorkflowStep"
      @take-manual-control="workflowAutomation.takeManualControl"
    />

    <!-- Advanced Step Confirmation Modal -->
    <AdvancedStepConfirmationModal
      :visible="showManualStepModal"
      :current-step="pendingWorkflowStep"
      :current-step-index="currentWorkflowStep"
      :workflow-steps="workflowSteps"
      :session-id="sessionId"
      @execute-step="workflowAutomation.executeConfirmedStep"
      @skip-step="workflowAutomation.skipCurrentStep"
      @take-manual-control="workflowAutomation.takeManualControl"
      @execute-all="workflowAutomation.executeAllRemainingSteps"
      @save-workflow="workflowAutomation.saveCustomWorkflow"
      @update-workflow="workflowAutomation.updateWorkflowSteps"
      @close="workflowAutomation.closeAdvancedModal"
    />

    <!-- Workflow Automation Logic Component -->
    <WorkflowAutomation
      ref="workflowAutomation"
      v-model:automation-paused="automationPaused"
      v-model:has-automated-workflow="hasAutomatedWorkflow"
      v-model:current-workflow-step="currentWorkflowStep"
      v-model:workflow-steps="workflowSteps"
      v-model:pending-workflow-step="pendingWorkflowStep"
      v-model:automation-queue="automationQueue"
      v-model:waiting-for-user-confirmation="waitingForUserConfirmation"
      @send-automation-control="sendAutomationControl"
      @execute-automated-command="executeAutomatedCommand"
      @add-output-line="addOutputLine"
      @add-running-process="addRunningProcess"
      @request-manual-step-confirmation="handleManualStepConfirmation"
    />
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useTerminalService } from '@/services/TerminalService.js'
import { useRoute, useRouter } from 'vue-router'

// Import sub-components
import TerminalHeader from './terminal/TerminalHeader.vue'
import TerminalStatusBar from './terminal/TerminalStatusBar.vue'
import TerminalOutput from './terminal/TerminalOutput.vue'
import TerminalInput from './terminal/TerminalInput.vue'
import TerminalModals from './terminal/TerminalModals.vue'
import WorkflowAutomation from './terminal/WorkflowAutomation.vue'
import AdvancedStepConfirmationModal from './AdvancedStepConfirmationModal.vue'

export default {
  name: 'TerminalWindow',
  components: {
    TerminalHeader,
    TerminalStatusBar,
    TerminalOutput,
    TerminalInput,
    TerminalModals,
    WorkflowAutomation,
    AdvancedStepConfirmationModal
  },
  props: {
    sessionId: {
      type: String,
      default: null
    },
    chatContext: {
      type: Boolean,
      default: false
    }
  },
  setup(props) {
    const route = useRoute()
    const router = useRouter()

    // Get the terminal service with all its methods
    const {
      sendInput,
      sendSignal,
      isConnected,
      resize,
      connect: connectToService,
      disconnect,
      createSession,
      closeSession
    } = useTerminalService()

    // Terminal session management
    const sessionId = ref(props.sessionId || null)

    // Initialize proper terminal session
    const initializeTerminalSession = async () => {
      try {
        // If in chat context and session ID provided via props, use it
        if (props.chatContext && props.sessionId) {
          sessionId.value = props.sessionId
          return props.sessionId
        }

        // Check if there's an existing terminal session ID in route params (standalone mode)
        if (route?.params?.sessionId || route?.query?.sessionId) {
          const existingSessionId = route.params.sessionId || route.query.sessionId
          sessionId.value = existingSessionId
          return existingSessionId
        }

        // Create a new terminal session using the API (standalone mode)
        const newSessionId = await createSession()
        sessionId.value = newSessionId
        return newSessionId
      } catch (error) {
        console.error('Failed to initialize terminal session:', error)
        // Fallback to a generated session ID if API fails
        const fallbackId = `terminal_${Date.now()}`
        sessionId.value = fallbackId
        return fallbackId
      }
    }

    const sessionTitle = ref(
      props.chatContext ? 'Chat Terminal' :
      route?.query?.title || 'Terminal'
    )
    const outputLines = ref([])
    const currentInput = ref('')
    const currentPrompt = ref('$ ')
    const connectionStatus = ref('disconnected')
    const connecting = ref(false)
    const showCursor = ref(true)
    const showReconnectModal = ref(false)
    const commandHistory = ref([])
    const historyIndex = ref(-1)

    // Safety and control state
    const showCommandConfirmation = ref(false)
    const showKillConfirmation = ref(false)
    const pendingCommand = ref('')
    const pendingCommandRisk = ref('low')
    const pendingCommandReasons = ref([])
    const runningProcesses = ref([])
    const hasActiveProcess = ref(false)

    // Automation control state
    const automationPaused = ref(false)
    const hasAutomatedWorkflow = ref(false)
    const currentWorkflowStep = ref(0)
    const workflowSteps = ref([])
    const showManualStepModal = ref(false)
    const showLegacyModal = ref(false)
    const pendingWorkflowStep = ref(null)
    const automationQueue = ref([])
    const waitingForUserConfirmation = ref(false)

    // Advanced workflow management state
    const isAdvancedMode = ref(true)
    const workflowTemplates = ref([])
    const passwordPromptActive = ref(false)
    const currentPasswordPrompt = ref(null)

    // Refs
    const terminalMain = ref(null)
    const terminalOutputComponent = ref(null)
    const terminalInputComponent = ref(null)
    const workflowAutomation = ref(null)

    // Computed properties
    const canInput = computed(() => {
      return connectionStatus.value === 'connected' &&
             !connecting.value &&
             !waitingForUserConfirmation.value
    })

    const hasRunningProcesses = computed(() => runningProcesses.value.length > 0)

    const connectionStatusText = computed(() => {
      switch (connectionStatus.value) {
        case 'connected': return 'Connected'
        case 'connecting': return 'Connecting...'
        case 'disconnected': return 'Disconnected'
        case 'error': return 'Error'
        default: return 'Unknown'
      }
    })

    // Methods
    const connect = async () => {
      if (!sessionId.value) {
        try {
          await initializeTerminalSession()
        } catch (error) {
          console.error('Failed to initialize terminal session:', error)
          return
        }
      }

      if (!sessionId.value) {
        console.error('No session ID available after initialization')
        return
      }

      connecting.value = true
      connectionStatus.value = 'connecting'

      try {
        await connectToService(sessionId.value, {
          onOutput: handleOutput,
          onPromptChange: handlePromptChange,
          onStatusChange: handleStatusChange,
          onError: handleError
        })
      } catch (error) {
        console.error('Failed to connect:', error)
        handleError(error.message)
      } finally {
        connecting.value = false
      }
    }

    const reconnect = async () => {
      hideReconnectModal()

      if (isConnected(sessionId.value)) {
        disconnect(sessionId.value)
      }

      outputLines.value = []
      currentPrompt.value = '$ '
      await connect()
    }

    // Enhanced sendCommand with safety checks
    const sendCommand = () => {
      if (!currentInput.value.trim() || !canInput.value) return

      const command = currentInput.value.trim()
      const riskAssessment = assessCommandRisk(command)

      if (riskAssessment.risk === 'high' || riskAssessment.risk === 'critical') {
        pendingCommand.value = command
        pendingCommandRisk.value = riskAssessment.risk
        pendingCommandReasons.value = riskAssessment.reasons
        showCommandConfirmation.value = true
        return
      }

      executeCommand(command)
    }

    // Execute command after safety checks
    const executeCommand = (command) => {
      // Add to command history
      if (command && (!commandHistory.value.length || commandHistory.value[commandHistory.value.length - 1] !== command)) {
        commandHistory.value.push(command)
        if (commandHistory.value.length > 100) {
          commandHistory.value = commandHistory.value.slice(-100)
        }
      }
      historyIndex.value = commandHistory.value.length

      // Track process start
      if (isProcessStartCommand(command)) {
        hasActiveProcess.value = true
        addRunningProcess(command)
      }

      // Send to terminal
      sendInput(sessionId.value, command)

      // Clear input
      currentInput.value = ''

      // Add command to output for immediate feedback
      addOutputLine({
        content: `${currentPrompt.value}${command}`,
        type: 'command',
        timestamp: new Date(),
        risk: pendingCommandRisk.value || 'low'
      })
    }

    // Command risk assessment
    const assessCommandRisk = (command) => {
      const lowerCmd = command.toLowerCase().trim()

      // Critical risk patterns (system destruction)
      const criticalPatterns = [
        /rm\s+-rf\s+\/($|\s)/,
        /dd\s+if=.*of=\/dev\/[sh]d/,
        /mkfs\./,
        /fdisk.*\/dev\/[sh]d/,
        />(\/etc\/passwd|\/etc\/shadow)/,
      ]

      // High risk patterns (data loss, system changes)
      const highRiskPatterns = [
        /rm\s+-rf/,
        /chmod\s+777.*\/$/,
        /chown.*\/$/,
        /rm\s+.*\/etc\//,
        /sudo\s+rm/,
        />\s*\/dev\/null.*&&.*rm/,
        /killall\s+-9/,
        /reboot|shutdown\s+-h/,
        /iptables\s+-F/,
        /userdel|groupdel/,
      ]

      // Moderate risk patterns (installations, configuration)
      const moderateRiskPatterns = [
        /sudo\s+(apt|yum|dnf|pacman).*install/,
        /sudo\s+(apt|yum|dnf|pacman).*remove/,
        /sudo\s+systemctl/,
        /sudo\s+(service|systemd)/,
        /sudo\s+mount/,
        /chmod.*[4-7][0-7][0-7]/,
        /sudo.*>/,
      ]

      let risk = 'low'
      const reasons = []

      // Check for critical patterns
      for (const pattern of criticalPatterns) {
        if (pattern.test(lowerCmd)) {
          risk = 'critical'
          reasons.push('Command could cause irreversible system damage')
          break
        }
      }

      // Check for high risk patterns
      if (risk === 'low') {
        for (const pattern of highRiskPatterns) {
          if (pattern.test(lowerCmd)) {
            risk = 'high'
            reasons.push('Command could delete data or modify system configuration')
            break
          }
        }
      }

      // Check for moderate risk patterns
      if (risk === 'low') {
        for (const pattern of moderateRiskPatterns) {
          if (pattern.test(lowerCmd)) {
            risk = 'moderate'
            reasons.push('Command requires elevated privileges or modifies system')
            break
          }
        }
      }

      // Additional risk factors
      if (lowerCmd.includes('sudo')) {
        reasons.push('Command uses sudo (elevated privileges)')
      }

      if (lowerCmd.includes('>>') || lowerCmd.includes('>')) {
        reasons.push('Command redirects output (potential file modification)')
      }

      return { risk, reasons }
    }

    // Safety control methods
    const executeConfirmedCommand = () => {
      executeCommand(pendingCommand.value)
      showCommandConfirmation.value = false
      pendingCommand.value = ''
      pendingCommandRisk.value = 'low'
      pendingCommandReasons.value = []
    }

    const cancelCommand = () => {
      showCommandConfirmation.value = false
      pendingCommand.value = ''
      pendingCommandRisk.value = 'low'
      pendingCommandReasons.value = []
      currentInput.value = ''
    }

    const emergencyKillAll = () => {
      if (runningProcesses.value.length === 0) {
        return
      }
      showKillConfirmation.value = true
    }

    const confirmEmergencyKill = async () => {
      try {
        await sendInput(sessionId.value, '\u0003\u0003\u0003')

        for (const process of runningProcesses.value) {
          try {
            await sendSignal(sessionId.value, 'SIGKILL', process.pid)
          } catch (error) {
            console.warn(`Failed to kill process ${process.pid}:`, error)
          }
        }

        runningProcesses.value = []
        hasActiveProcess.value = false

        addOutputLine({
          content: '🛑 EMERGENCY KILL: All processes terminated by user',
          type: 'system_message',
          timestamp: new Date()
        })

        showKillConfirmation.value = false

      } catch (error) {
        console.error('Emergency kill failed:', error)
        addOutputLine({
          content: '❌ Emergency kill failed: ' + error.message,
          type: 'error',
          timestamp: new Date()
        })
      }
    }

    const interruptProcess = () => {
      if (!hasActiveProcess.value) return

      sendInput(sessionId.value, '\u0003')

      addOutputLine({
        content: '^C (Process interrupted by user)',
        type: 'system_message',
        timestamp: new Date()
      })
    }

    // Process tracking helpers
    const isProcessStartCommand = (command) => {
      const processStartPatterns = [
        /^(vim|nano|emacs|less|more|top|htop|tail\s+-f)/,
        /&\s*$/,
        /^(python|node|java|go)/,
        /^(ssh|scp|rsync)/,
        /^(find|grep|sort).*\|/,
      ]

      return processStartPatterns.some(pattern => pattern.test(command.toLowerCase()))
    }

    const addRunningProcess = (command) => {
      const process = {
        pid: Date.now(),
        command: command,
        startTime: new Date()
      }

      runningProcesses.value.push(process)
    }

    // History navigation
    const handleHistoryNavigation = (direction, index) => {
      if (direction === 'up' && index >= 0 && index < commandHistory.value.length) {
        currentInput.value = commandHistory.value[index]
        historyIndex.value = index
      } else if (direction === 'down' && index >= 0 && index < commandHistory.value.length) {
        currentInput.value = commandHistory.value[index]
        historyIndex.value = index
      }
    }

    const sendExitSignal = () => {
      sendInput(sessionId.value, 'exit')
    }

    const clearTerminal = () => {
      outputLines.value = []
    }

    const focusInput = () => {
      terminalInputComponent.value?.focusInput()
    }

    const closeWindow = () => {
      if (confirm('Are you sure you want to close this terminal window?')) {
        if (isConnected(sessionId.value)) {
          disconnect(sessionId.value)
        }
        window.close()
      }
    }

    const downloadLog = () => {
      const logContent = outputLines.value
        .map(line => {
          const timestamp = line.timestamp ? `[${line.timestamp.toLocaleString()}] ` : ''
          return `${timestamp}${line.content || line}`
        })
        .join('\n')

      const blob = new Blob([logContent], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `terminal-${sessionId.value}-${new Date().toISOString().split('T')[0]}.log`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }

    const shareSession = async () => {
      const url = `${window.location.origin}/terminal/${sessionId.value}?title=${encodeURIComponent(sessionTitle.value)}`

      if (navigator.share) {
        try {
          await navigator.share({
            title: `Terminal Session - ${sessionTitle.value}`,
            url: url
          })
        } catch (error) {
          if (error.name !== 'AbortError') {
            console.warn('Share operation failed:', error)
          }
        }
      } else {
        try {
          await navigator.clipboard.writeText(url)
          alert('Terminal URL copied to clipboard!')
        } catch (error) {
          prompt('Copy this URL:', url)
        }
      }
    }

    const hideReconnectModal = () => {
      showReconnectModal.value = false
    }

    // Automation control methods
    const sendAutomationControl = async (action) => {
      try {
        const controlMessage = {
          type: 'automation_control',
          action: action,
          sessionId: sessionId.value,
          timestamp: new Date().toISOString()
        }

        await sendInput(sessionId.value, JSON.stringify(controlMessage))
      } catch (error) {
        console.error('Failed to send automation control:', error)
      }
    }

    const executeAutomatedCommand = (command) => {
      sendInput(sessionId.value, command)
      hasActiveProcess.value = true
      addRunningProcess(`[AUTO] ${command}`)
    }

    const handleManualStepConfirmation = (stepInfo) => {
      showManualStepModal.value = true
    }

    // Terminal event handlers
    const handleOutput = (data) => {
      addOutputLine({
        content: data.content,
        type: data.stream || 'output',
        timestamp: new Date()
      })
    }

    const handlePromptChange = (prompt) => {
      currentPrompt.value = prompt
    }

    const handleStatusChange = (status) => {
      connectionStatus.value = status

      if (status === 'connected') {
        connecting.value = false
        nextTick(() => {
          setTimeout(() => {
            if (canInput.value) {
              focusInput()
            }
          }, 50)
        })
      } else if (status === 'disconnected' && !connecting.value) {
        showReconnectModal.value = true
      } else if (status === 'connecting') {
        connecting.value = true
      }
    }

    const handleError = (error) => {
      addOutputLine({
        content: `Error: ${error}`,
        type: 'error',
        timestamp: new Date()
      })
      connectionStatus.value = 'error'
    }

    const addOutputLine = (line) => {
      outputLines.value.push(line)

      if (outputLines.value.length > 10000) {
        outputLines.value = outputLines.value.slice(-8000)
      }
    }

    // Cursor blinking effect
    const startCursorBlink = () => {
      setInterval(() => {
        showCursor.value = !showCursor.value
      }, 500)
    }

    // Handle window resize
    const handleResize = () => {
      if (terminalMain.value && isConnected(sessionId.value)) {
        const rect = terminalMain.value.getBoundingClientRect()
        const charWidth = 8
        const charHeight = 16
        const cols = Math.floor((rect.width - 20) / charWidth)
        const rows = Math.floor((rect.height - 100) / charHeight)
        resize(sessionId.value, rows, cols)
      }
    }

    // Handle window beforeunload
    const handleBeforeUnload = (event) => {
      if (isConnected(sessionId.value)) {
        event.preventDefault()
        event.returnValue = 'You have an active terminal session. Are you sure you want to close?'
        return event.returnValue
      }
    }

    // Lifecycle
    onMounted(async () => {
      startCursorBlink()
      document.title = `Terminal - ${sessionTitle.value}`
      await connect()
      window.addEventListener('resize', handleResize)
      window.addEventListener('beforeunload', handleBeforeUnload)
      nextTick(() => {
        focusInput()
      })
    })

    onUnmounted(() => {
      if (isConnected && typeof isConnected === 'function' && isConnected(sessionId.value)) {
        disconnect(sessionId.value)
      }
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('beforeunload', handleBeforeUnload)
    })

    // Watch for route changes
    watch(() => route.params.sessionId, (newSessionId) => {
      if (newSessionId && newSessionId !== sessionId.value) {
        if (sessionId.value && isConnected(sessionId.value)) {
          disconnect(sessionId.value)
        }
        sessionId.value = newSessionId
        outputLines.value = []
        connect()
      }
    })

    return {
      // Data
      sessionId,
      sessionTitle,
      outputLines,
      currentInput,
      currentPrompt,
      connectionStatus,
      connecting,
      showCursor,
      showReconnectModal,
      showCommandConfirmation,
      showKillConfirmation,
      pendingCommand,
      pendingCommandRisk,
      pendingCommandReasons,
      runningProcesses,
      hasActiveProcess,
      commandHistory,

      // Automation Control Data
      automationPaused,
      hasAutomatedWorkflow,
      currentWorkflowStep,
      workflowSteps,
      showManualStepModal,
      showLegacyModal,
      pendingWorkflowStep,
      automationQueue,
      waitingForUserConfirmation,

      // Refs
      terminalMain,
      terminalOutputComponent,
      terminalInputComponent,
      workflowAutomation,

      // Computed
      canInput,
      hasRunningProcesses,
      connectionStatusText,

      // Methods
      connect,
      reconnect,
      sendCommand,
      executeCommand,
      executeConfirmedCommand,
      cancelCommand,
      emergencyKillAll,
      confirmEmergencyKill,
      interruptProcess,
      handleHistoryNavigation,
      sendExitSignal,
      clearTerminal,
      focusInput,
      closeWindow,
      downloadLog,
      shareSession,
      hideReconnectModal,
      sendAutomationControl,
      executeAutomatedCommand,
      handleManualStepConfirmation,
      addOutputLine,
      addRunningProcess
    }
  }
}
</script>

<style scoped>
.terminal-window-standalone {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #000;
  color: #ffffff;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  overflow: hidden;
}

.terminal-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Responsive */
@media (max-width: 768px) {
  .terminal-window-standalone {
    font-size: 12px;
  }
}
</style>