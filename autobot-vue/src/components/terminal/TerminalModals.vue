<template>
  <div>
    <!-- Connection Lost Modal -->
    <div
      v-if="showReconnectModal"
      class="modal-overlay"
      @click="$emit('hide-reconnect-modal')"
      tabindex="0"
      @keyup.enter="$event.target.click()"
      @keyup.space="$event.target.click()"
    >
      <div class="modal-content" @click.stop>
        <h3>Connection Lost</h3>
        <p>The terminal connection was lost. Would you like to reconnect?</p>

        <!-- Error Display -->
        <div v-if="connectionError" class="error-message">
          <div class="error-icon">⚠️</div>
          <div class="error-text">{{ connectionError }}</div>
        </div>

        <!-- Success Display -->
        <div v-if="connectionSuccess" class="success-message">
          <div class="success-icon">✅</div>
          <div class="success-text">{{ connectionSuccess }}</div>
        </div>

        <div class="modal-actions">
          <BaseButton
            variant="secondary"
            @click="$emit('hide-reconnect-modal')"
            :disabled="isReconnecting"
          >
            Cancel
          </BaseButton>
          <BaseButton
            variant="primary"
            @click="handleReconnect"
            :loading="isReconnecting"
          >
            {{ isReconnecting ? 'Reconnecting...' : 'Reconnect' }}
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Command Confirmation Modal -->
    <div
      v-if="showCommandConfirmation"
      class="confirmation-modal-overlay"
      @click="cancelCommand"
      tabindex="0"
      @keyup.enter="$event.target.click()"
      @keyup.space="$event.target.click()"
    >
      <div class="confirmation-modal" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">⚠️ Potentially Destructive Command</h3>
        </div>
        <div class="modal-content">
          <div class="command-preview">
            <div class="command-label">Command to execute:</div>
            <div class="command-text">{{ pendingCommand }}</div>
          </div>

          <div class="risk-assessment">
            <div class="risk-level" :class="pendingCommandRisk">
              Risk Level: <strong>{{ pendingCommandRisk.toUpperCase() }}</strong>
            </div>
            <div class="risk-reasons">
              <div v-for="reason in pendingCommandReasons" :key="reason" class="risk-reason">
                • {{ reason }}
              </div>
            </div>
          </div>

          <!-- Error Display -->
          <div v-if="commandError" class="error-message">
            <div class="error-icon">⚠️</div>
            <div class="error-text">{{ commandError }}</div>
          </div>

          <!-- Success Display -->
          <div v-if="commandSuccess" class="success-message">
            <div class="success-icon">✅</div>
            <div class="success-text">{{ commandSuccess }}</div>
          </div>

          <div class="confirmation-message">
            <p><strong>This command may:</strong></p>
            <ul>
              <li>Delete files or directories permanently</li>
              <li>Modify system configurations</li>
              <li>Change file permissions or ownership</li>
              <li>Install or remove software packages</li>
            </ul>
            <p><strong>Are you sure you want to proceed?</strong></p>
          </div>
        </div>

        <div class="modal-actions">
          <BaseButton
            variant="danger"
            @click="handleExecuteCommand"
            :loading="isExecutingCommand"
          >
            {{ isExecutingCommand ? 'Executing...' : '⚡ Execute Command' }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="cancelCommand"
            :disabled="isExecutingCommand"
          >
            ❌ Cancel
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Emergency Kill Confirmation Modal -->
    <div
      v-if="showKillConfirmation"
      class="confirmation-modal-overlay"
      @click="cancelKill"
      tabindex="0"
      @keyup.enter="$event.target.click()"
      @keyup.space="$event.target.click()"
    >
      <div class="confirmation-modal emergency" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">🛑 Emergency Kill All Processes</h3>
        </div>
        <div class="modal-content">
          <div class="emergency-warning">
            <p><strong>⚠️ WARNING: This will immediately terminate ALL running processes in this terminal session!</strong></p>
            <p>Running processes:</p>
            <ul>
              <li v-for="process in runningProcesses" :key="process.pid" class="process-item">
                PID {{ process.pid }}: {{ process.command }}
              </li>
            </ul>
            <p><strong>This action cannot be undone. Continue?</strong></p>
          </div>

          <!-- Error Display -->
          <div v-if="killError" class="error-message">
            <div class="error-icon">⚠️</div>
            <div class="error-text">{{ killError }}</div>
          </div>

          <!-- Success Display -->
          <div v-if="killSuccess" class="success-message">
            <div class="success-icon">✅</div>
            <div class="success-text">{{ killSuccess }}</div>
          </div>
        </div>

        <div class="modal-actions">
          <BaseButton
            variant="danger"
            @click="handleEmergencyKill"
            :loading="isKillingProcesses"
          >
            {{ isKillingProcesses ? 'Killing Processes...' : '🛑 KILL ALL PROCESSES' }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="cancelKill"
            :disabled="isKillingProcesses"
          >
            ❌ Cancel
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Legacy Manual Step Confirmation Modal -->
    <div
      v-if="showLegacyModal"
      class="confirmation-modal-overlay"
      @click="handleTakeManualControl"
      tabindex="0"
      @keyup.enter="$event.target.click()"
      @keyup.space="$event.target.click()"
    >
      <div class="confirmation-modal workflow-step" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">🤖 AI Workflow Step Confirmation</h3>
        </div>
        <div class="modal-content">
          <div class="workflow-step-info" v-if="pendingWorkflowStep">
            <div class="step-counter">
              Step {{ pendingWorkflowStep.stepNumber }} of {{ pendingWorkflowStep.totalSteps }}
            </div>

            <div class="step-description">
              <h4>{{ pendingWorkflowStep.description }}</h4>
              <p>{{ pendingWorkflowStep.explanation || 'The AI wants to execute the following command:' }}</p>
            </div>

            <div class="command-preview">
              <div class="command-label">Command to Execute:</div>
              <div class="command-text">{{ pendingWorkflowStep.command }}</div>
            </div>

            <!-- Error Display -->
            <div v-if="workflowError" class="error-message">
              <div class="error-icon">⚠️</div>
              <div class="error-text">{{ workflowError }}</div>
            </div>

            <!-- Success Display -->
            <div v-if="workflowSuccess" class="success-message">
              <div class="success-icon">✅</div>
              <div class="success-text">{{ workflowSuccess }}</div>
            </div>

            <div class="workflow-options">
              <div class="option-info">
                <p><strong>Choose your action:</strong></p>
                <ul>
                  <li><strong>Execute:</strong> Run this command and continue to next step</li>
                  <li><strong>Skip:</strong> Skip this command and continue to next step</li>
                  <li><strong>Take Control:</strong> Pause automation and perform manual steps</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-actions workflow-actions">
          <BaseButton
            variant="success"
            @click="handleConfirmWorkflowStep"
            :loading="isProcessingWorkflow && lastWorkflowAction === 'execute'"
            :disabled="isProcessingWorkflow && lastWorkflowAction !== 'execute'"
          >
            {{ (isProcessingWorkflow && lastWorkflowAction === 'execute') ? 'Executing...' : '✅ Execute & Continue' }}
          </BaseButton>
          <BaseButton
            variant="warning"
            @click="handleSkipWorkflowStep"
            :loading="isProcessingWorkflow && lastWorkflowAction === 'skip'"
            :disabled="isProcessingWorkflow && lastWorkflowAction !== 'skip'"
          >
            {{ (isProcessingWorkflow && lastWorkflowAction === 'skip') ? 'Skipping...' : '⏭️ Skip This Step' }}
          </BaseButton>
          <BaseButton
            variant="primary"
            @click="handleTakeManualControl"
            :loading="isProcessingWorkflow && lastWorkflowAction === 'manual'"
            :disabled="isProcessingWorkflow && lastWorkflowAction !== 'manual'"
          >
            {{ (isProcessingWorkflow && lastWorkflowAction === 'manual') ? 'Taking Control...' : '👤 Take Manual Control' }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface ProcessInfo {
  pid: number
  command: string
  startTime?: Date
}

interface WorkflowStep {
  stepNumber: number
  totalSteps: number
  command: string
  description?: string
  explanation?: string
}

interface Props {
  showReconnectModal: boolean
  showCommandConfirmation: boolean
  showKillConfirmation: boolean
  showLegacyModal: boolean
  pendingCommand: string
  pendingCommandRisk: string
  pendingCommandReasons: string[]
  runningProcesses: ProcessInfo[]
  pendingWorkflowStep: WorkflowStep | null
}

interface Emits {
  (e: 'hide-reconnect-modal'): void
  (e: 'reconnect'): void
  (e: 'cancel-command'): void
  (e: 'execute-confirmed-command'): void
  (e: 'cancel-kill'): void
  (e: 'confirm-emergency-kill'): void
  (e: 'confirm-workflow-step'): void
  (e: 'skip-workflow-step'): void
  (e: 'take-manual-control'): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

// Loading states
const isReconnecting = ref(false)
const isExecutingCommand = ref(false)
const isKillingProcesses = ref(false)
const isProcessingWorkflow = ref(false)
const lastWorkflowAction = ref<'execute' | 'skip' | 'manual' | null>(null)

// Error states
const connectionError = ref('')
const connectionSuccess = ref('')
const commandError = ref('')
const commandSuccess = ref('')
const killError = ref('')
const killSuccess = ref('')
const workflowError = ref('')
const workflowSuccess = ref('')

// Timeout configurations
const RECONNECT_TIMEOUT = 10000 // 10 seconds
const COMMAND_TIMEOUT = 30000   // 30 seconds
const KILL_TIMEOUT = 15000      // 15 seconds
const WORKFLOW_TIMEOUT = 20000  // 20 seconds

// Utility function to clear all messages
const clearMessages = () => {
  connectionError.value = ''
  connectionSuccess.value = ''
  commandError.value = ''
  commandSuccess.value = ''
  killError.value = ''
  killSuccess.value = ''
  workflowError.value = ''
  workflowSuccess.value = ''
}

// Standard error handler
const handleError = (error: any, setter: (msg: string) => void) => {
  console.error('Terminal modal error:', error)

  let errorMessage = 'An unexpected error occurred'

  if (error?.message) {
    errorMessage = error.message
  } else if (error?.response?.data?.detail) {
    errorMessage = error.response.data.detail
  } else if (error?.response?.status === 408) {
    errorMessage = 'Request timed out. Please try again.'
  } else if (error?.response?.status === 500) {
    errorMessage = 'Server error. Please try again later.'
  } else if (error?.response?.status === 404) {
    errorMessage = 'Service not found. Please check your connection.'
  } else if (typeof error === 'string') {
    errorMessage = error
  }

  setter(errorMessage)

  // Auto-hide error after 10 seconds
  setTimeout(() => {
    setter('')
  }, 10000)
}

// Standard success handler
const handleSuccess = (message: string, setter: (msg: string) => void) => {
  setter(message)

  // Auto-hide success after 5 seconds
  setTimeout(() => {
    setter('')
  }, 5000)
}

// Enhanced action handlers with error handling and loading states
const handleReconnect = async () => {
  if (isReconnecting.value) return

  clearMessages()
  isReconnecting.value = true

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Reconnection timed out')), RECONNECT_TIMEOUT)
    })

    // Create reconnection promise
    const reconnectPromise = new Promise<void>((resolve) => {
      emit('reconnect')
      // Simulate async operation
      setTimeout(resolve, 1000)
    })

    await Promise.race([reconnectPromise, timeoutPromise])

    handleSuccess('Successfully reconnected to terminal', (msg) => connectionSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => connectionError.value = msg)
  } finally {
    isReconnecting.value = false
  }
}

const handleExecuteCommand = async () => {
  if (isExecutingCommand.value) return

  clearMessages()
  isExecutingCommand.value = true

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Command execution timed out')), COMMAND_TIMEOUT)
    })

    // Create execution promise
    const executePromise = new Promise<void>((resolve) => {
      emit('execute-confirmed-command')
      // Simulate async operation
      setTimeout(resolve, 1500)
    })

    await Promise.race([executePromise, timeoutPromise])

    handleSuccess('Command executed successfully', (msg) => commandSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => commandError.value = msg)
  } finally {
    isExecutingCommand.value = false
  }
}

const cancelCommand = () => {
  if (isExecutingCommand.value) return
  clearMessages()
  emit('cancel-command')
}

const handleEmergencyKill = async () => {
  if (isKillingProcesses.value) return

  clearMessages()
  isKillingProcesses.value = true

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Process termination timed out')), KILL_TIMEOUT)
    })

    // Create kill promise
    const killPromise = new Promise<void>((resolve) => {
      emit('confirm-emergency-kill')
      // Simulate async operation
      setTimeout(resolve, 2000)
    })

    await Promise.race([killPromise, timeoutPromise])

    handleSuccess('All processes terminated successfully', (msg) => killSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => killError.value = msg)
  } finally {
    isKillingProcesses.value = false
  }
}

const cancelKill = () => {
  if (isKillingProcesses.value) return
  clearMessages()
  emit('cancel-kill')
}

const handleConfirmWorkflowStep = async () => {
  if (isProcessingWorkflow.value) return

  clearMessages()
  isProcessingWorkflow.value = true
  lastWorkflowAction.value = 'execute'

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Workflow step execution timed out')), WORKFLOW_TIMEOUT)
    })

    // Create workflow promise
    const workflowPromise = new Promise<void>((resolve) => {
      emit('confirm-workflow-step')
      // Simulate async operation
      setTimeout(resolve, 1200)
    })

    await Promise.race([workflowPromise, timeoutPromise])

    handleSuccess('Workflow step executed successfully', (msg) => workflowSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => workflowError.value = msg)
  } finally {
    isProcessingWorkflow.value = false
    lastWorkflowAction.value = null
  }
}

const handleSkipWorkflowStep = async () => {
  if (isProcessingWorkflow.value) return

  clearMessages()
  isProcessingWorkflow.value = true
  lastWorkflowAction.value = 'skip'

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Workflow step skip timed out')), WORKFLOW_TIMEOUT)
    })

    // Create skip promise
    const skipPromise = new Promise<void>((resolve) => {
      emit('skip-workflow-step')
      // Simulate async operation
      setTimeout(resolve, 800)
    })

    await Promise.race([skipPromise, timeoutPromise])

    handleSuccess('Workflow step skipped successfully', (msg) => workflowSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => workflowError.value = msg)
  } finally {
    isProcessingWorkflow.value = false
    lastWorkflowAction.value = null
  }
}

const handleTakeManualControl = async () => {
  if (isProcessingWorkflow.value) return

  clearMessages()
  isProcessingWorkflow.value = true
  lastWorkflowAction.value = 'manual'

  try {
    // Create timeout promise
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Manual control transition timed out')), WORKFLOW_TIMEOUT)
    })

    // Create manual control promise
    const manualPromise = new Promise<void>((resolve) => {
      emit('take-manual-control')
      // Simulate async operation
      setTimeout(resolve, 1000)
    })

    await Promise.race([manualPromise, timeoutPromise])

    handleSuccess('Manual control activated successfully', (msg) => workflowSuccess.value = msg)

  } catch (error) {
    handleError(error, (msg) => workflowError.value = msg)
  } finally {
    isProcessingWorkflow.value = false
    lastWorkflowAction.value = null
  }
}
</script>

<style scoped>
/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background-color: #2d2d2d;
  color: #fff;
  padding: 24px;
  border-radius: 8px;
  max-width: 400px;
  width: 90%;
  text-align: center;
}

.modal-content h3 {
  margin-top: 0;
  color: #ffc107;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
}

/* Error and Success Messages */
.error-message, .success-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  border-radius: 6px;
  margin: 16px 0;
  font-size: 14px;
  line-height: 1.4;
}

.error-message {
  background-color: rgba(220, 53, 69, 0.1);
  border: 1px solid rgba(220, 53, 69, 0.3);
  color: #ff6b6b;
}

.success-message {
  background-color: rgba(40, 167, 69, 0.1);
  border: 1px solid rgba(40, 167, 69, 0.3);
  color: #28a745;
}

.error-icon, .success-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.error-text, .success-text {
  flex: 1;
  word-break: break-word;
}

/* Command confirmation modal styles */
.confirmation-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(2px);
}

.confirmation-modal {
  background-color: #2d2d2d;
  color: #fff;
  padding: 0;
  border-radius: 12px;
  max-width: 600px;
  width: 90%;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  border: 1px solid #444;
}

.confirmation-modal.emergency {
  border-color: #dc3545;
  box-shadow: 0 10px 30px rgba(220, 53, 69, 0.3);
}

.confirmation-modal.workflow-step {
  max-width: 700px;
  border-color: #17a2b8;
  box-shadow: 0 10px 30px rgba(23, 162, 184, 0.3);
}

.modal-header {
  padding: 20px 24px 16px 24px;
  border-bottom: 1px solid #444;
  background: linear-gradient(135deg, #333 0%, #2d2d2d 100%);
  border-radius: 12px 12px 0 0;
}

.modal-title {
  margin: 0;
  color: #ffc107;
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.confirmation-modal.emergency .modal-title {
  color: #ff6b6b;
}

.modal-content {
  padding: 24px;
}

.command-preview {
  background-color: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.command-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.command-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  color: #87ceeb;
  background-color: #000;
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid #ffc107;
  white-space: pre-wrap;
  word-break: break-all;
}

.risk-assessment {
  margin-bottom: 20px;
}

.risk-level {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.risk-level.low {
  background-color: rgba(40, 167, 69, 0.2);
  color: #28a745;
  border: 1px solid #28a745;
}

.risk-level.moderate {
  background-color: rgba(255, 193, 7, 0.2);
  color: #ffc107;
  border: 1px solid #ffc107;
}

.risk-level.high {
  background-color: rgba(255, 107, 107, 0.2);
  color: #ff6b6b;
  border: 1px solid #ff6b6b;
}

.risk-level.critical {
  background-color: rgba(220, 53, 69, 0.3);
  color: #ff4757;
  border: 1px solid #dc3545;
  animation: pulse-danger 2s infinite;
}

.risk-reasons {
  color: #ccc;
}

.risk-reason {
  margin-bottom: 4px;
  font-size: 13px;
}

.confirmation-message {
  color: #ddd;
}

.confirmation-message p {
  margin-bottom: 12px;
}

.confirmation-message ul {
  margin: 12px 0;
  padding-left: 20px;
}

.confirmation-message li {
  margin-bottom: 6px;
  color: #ccc;
}

.emergency-warning {
  color: #ff6b6b;
}

.emergency-warning p {
  margin-bottom: 12px;
  font-weight: 500;
}

.process-item {
  background-color: #1e1e1e;
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  color: #87ceeb;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 20px 24px;
  border-top: 1px solid #444;
  background-color: #252525;
  border-radius: 0 0 12px 12px;
}

.workflow-actions {
  justify-content: space-between;
  padding: 20px 24px;
}

/* Workflow Step Modal Styles */
.workflow-step-info {
  text-align: left;
}

.step-counter {
  background-color: #17a2b8;
  color: white;
  padding: 8px 16px;
  border-radius: 20px;
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.step-description h4 {
  margin: 0 0 8px 0;
  color: #17a2b8;
  font-size: 16px;
  font-weight: 600;
}

.step-description p {
  margin: 0 0 16px 0;
  color: #ccc;
  font-size: 14px;
  line-height: 1.5;
}

.workflow-options {
  background-color: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  margin-top: 20px;
  border-left: 4px solid #17a2b8;
}

.option-info p {
  margin: 0 0 12px 0;
  color: #17a2b8;
  font-weight: 600;
}

.option-info ul {
  margin: 0;
  padding-left: 20px;
  color: #ccc;
}

.option-info li {
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.4;
}

.option-info li strong {
  color: #fff;
}

/* Enhanced animations */
@keyframes pulse-danger {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(220, 53, 69, 0);
  }
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .modal-content {
    max-width: 95%;
    padding: 16px;
  }

  .confirmation-modal {
    max-width: 95%;
  }

  .modal-actions {
    flex-direction: column;
    gap: 8px;
  }

  .workflow-actions {
    flex-direction: column;
    gap: 8px;
  }

  .command-text {
    font-size: 12px;
    padding: 8px;
  }

  .modal-header {
    padding: 16px 20px 12px 20px;
  }

  .modal-title {
    font-size: 16px;
  }
}

@media (max-width: 480px) {
  .confirmation-modal {
    margin: 10px;
  }

  .modal-content {
    padding: 12px;
  }

  .modal-header {
    padding: 12px 16px 8px 16px;
  }

  .modal-actions {
    padding: 16px;
  }
}
</style>