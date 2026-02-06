<template>
  <div>
    <!-- Connection Lost Modal -->
    <BaseModal
      :modelValue="showReconnectModal"
      @update:modelValue="val => !val && $emit('hide-reconnect-modal')"
      title="Connection Lost"
      size="small"
      :closeOnOverlay="!isReconnecting"
    >
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

      <template #actions>
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
      </template>
    </BaseModal>

    <!-- Command Confirmation Modal -->
    <BaseModal
      :modelValue="showCommandConfirmation"
      @update:modelValue="val => !val && cancelCommand()"
      title="⚠️ Potentially Destructive Command"
      size="medium"
      :closeOnOverlay="!isExecutingCommand"
      class="command-confirmation-modal"
    >
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

      <template #actions>
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
      </template>
    </BaseModal>

    <!-- Emergency Kill Confirmation Modal -->
    <BaseModal
      :modelValue="showKillConfirmation"
      @update:modelValue="val => !val && cancelKill()"
      title="🛑 Emergency Kill All Processes"
      size="medium"
      :closeOnOverlay="!isKillingProcesses"
      class="emergency-kill-modal"
    >
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

      <template #actions>
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
      </template>
    </BaseModal>

    <!-- Legacy Manual Step Confirmation Modal -->
    <BaseModal
      :modelValue="showLegacyModal"
      @update:modelValue="val => !val && handleTakeManualControl()"
      title="🤖 AI Workflow Step Confirmation"
      size="large"
      :closeOnOverlay="!isProcessingWorkflow"
      class="workflow-step-modal"
    >
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

      <template #actions>
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
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'

const logger = createLogger('TerminalModals')
import BaseModal from '@/components/ui/BaseModal.vue'

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
  logger.error('Terminal modal error:', error)

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
/* Issue #704: Migrated to CSS design tokens */
/* Error and Success Messages */
.error-message, .success-message {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  margin: var(--spacing-4) 0;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.error-message {
  background-color: var(--color-error-bg-transparent);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
}

.success-message {
  background-color: var(--color-success-bg-transparent);
  border: 1px solid var(--color-success-border);
  color: var(--color-success);
}

.error-icon, .success-icon {
  flex-shrink: 0;
  font-size: var(--text-base);
}

.error-text, .success-text {
  flex: 1;
  word-break: break-word;
}

/* Content-specific styles */
.command-preview {
  background-color: var(--terminal-bg);
  border: 1px solid var(--terminal-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.command-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.command-text {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--terminal-cyan);
  background-color: var(--terminal-bg-dark);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-warning);
  white-space: pre-wrap;
  word-break: break-all;
}

.risk-assessment {
  margin-bottom: var(--spacing-5);
}

.risk-level {
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-3);
}

.risk-level.low {
  background-color: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success);
}

.risk-level.moderate {
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

.risk-level.high {
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
}

.risk-level.critical {
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  animation: pulse-danger 2s infinite;
}

.risk-reasons {
  color: var(--text-secondary);
}

.risk-reason {
  margin-bottom: var(--spacing-1);
  font-size: var(--text-xs);
}

.confirmation-message {
  color: var(--text-secondary);
}

.confirmation-message p {
  margin-bottom: var(--spacing-3);
}

.confirmation-message ul {
  margin: var(--spacing-3) 0;
  padding-left: var(--spacing-5);
}

.confirmation-message li {
  margin-bottom: var(--spacing-1-5);
  color: var(--text-secondary);
}

.emergency-warning {
  color: var(--color-error);
}

.emergency-warning p {
  margin-bottom: var(--spacing-3);
  font-weight: var(--font-medium);
}

.process-item {
  background-color: var(--terminal-bg);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-1);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--terminal-cyan);
}

/* Workflow Step Modal Styles */
.workflow-step-info {
  text-align: left;
}

.step-counter {
  background-color: var(--color-info);
  color: var(--text-on-primary);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-full);
  display: inline-block;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-4);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.step-description h4 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--color-info);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.step-description p {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}

.workflow-options {
  background-color: var(--terminal-bg);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-top: var(--spacing-5);
  border-left: 4px solid var(--color-info);
}

.option-info p {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--color-info);
  font-weight: var(--font-semibold);
}

.option-info ul {
  margin: 0;
  padding-left: var(--spacing-5);
  color: var(--text-secondary);
}

.option-info li {
  margin-bottom: var(--spacing-2);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.option-info li strong {
  color: var(--text-primary);
}

/* Enhanced animations */
@keyframes pulse-danger {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--color-error-shadow);
  }
  50% {
    box-shadow: 0 0 0 8px transparent;
  }
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .command-text {
    font-size: var(--text-xs);
    padding: var(--spacing-2);
  }
}
</style>
