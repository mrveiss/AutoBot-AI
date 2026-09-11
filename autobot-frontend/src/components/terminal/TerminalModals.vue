<template>
  <div>
    <!-- Connection Lost Modal -->
    <BaseModal
      :close-label="t('ui.modal.closeDialog')"
      :modelValue="showReconnectModal"
      @update:modelValue="val => !val && $emit('hide-reconnect-modal')"
      :title="$t('terminal.modals.connectionLost')"
      size="sm"
      :closeOnOverlay="!isReconnecting"
    >
      <p>{{ $t('terminal.modals.connectionLostMsg') }}</p>

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
          {{ $t('common.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          @click="handleReconnect"
          :loading="isReconnecting"
        >
          {{ isReconnecting ? $t('terminal.modals.reconnecting') : $t('terminal.reconnect') }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Command Confirmation Modal -->
    <BaseModal
      :close-label="t('ui.modal.closeDialog')"
      :modelValue="showCommandConfirmation"
      @update:modelValue="val => !val && cancelCommand()"
      :title="$t('terminal.modals.destructiveCommand')"
      size="md"
      :closeOnOverlay="!isExecutingCommand"
      class="command-confirmation-modal"
    >
      <div class="command-preview">
        <div class="command-label">{{ $t('terminal.modals.commandLabel') }}</div>
        <div class="command-text">{{ pendingCommand }}</div>
      </div>

      <div class="risk-assessment">
        <div class="risk-level" :class="pendingCommandRisk">
          {{ $t('terminal.modals.riskLevel') }} <strong>{{ pendingCommandRisk.toUpperCase() }}</strong>
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
        <p><strong>{{ $t('terminal.modals.commandMay') }}</strong></p>
        <ul>
          <li>{{ $t('terminal.modals.deleteFiles') }}</li>
          <li>{{ $t('terminal.modals.modifyConfig') }}</li>
          <li>{{ $t('terminal.modals.changePermissions') }}</li>
          <li>{{ $t('terminal.modals.installRemove') }}</li>
        </ul>
        <p><strong>{{ $t('terminal.modals.confirmProceed') }}</strong></p>
      </div>

      <template #actions>
        <BaseButton
          variant="error"
          @click="handleExecuteCommand"
          :loading="isExecutingCommand"
        >
          {{ isExecutingCommand ? $t('terminal.modals.executing') : $t('terminal.modals.executeCommand') }}
        </BaseButton>
        <BaseButton
          variant="secondary"
          @click="cancelCommand"
          :disabled="isExecutingCommand"
        >
          {{ $t('common.cancel') }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Emergency Kill Confirmation Modal -->
    <BaseModal
      :close-label="t('ui.modal.closeDialog')"
      :modelValue="showKillConfirmation"
      @update:modelValue="val => !val && cancelKill()"
      :title="$t('terminal.modals.emergencyKillTitle')"
      size="md"
      :closeOnOverlay="!isKillingProcesses"
      class="emergency-kill-modal"
    >
      <div class="emergency-warning">
        <p><strong>{{ $t('terminal.modals.emergencyWarning') }}</strong></p>
        <p>{{ $t('terminal.modals.runningProcesses') }}</p>
        <ul>
          <li v-for="process in runningProcesses" :key="process.pid" class="process-item">
            PID {{ process.pid }}: {{ process.command }}
          </li>
        </ul>
        <p><strong>{{ $t('terminal.modals.cannotUndo') }}</strong></p>
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
          variant="error"
          @click="handleEmergencyKill"
          :loading="isKillingProcesses"
        >
          {{ isKillingProcesses ? $t('terminal.modals.killingProcesses') : $t('terminal.modals.killAll') }}
        </BaseButton>
        <BaseButton
          variant="secondary"
          @click="cancelKill"
          :disabled="isKillingProcesses"
        >
          {{ $t('common.cancel') }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Legacy Manual Step Confirmation Modal -->
    <BaseModal
      :close-label="t('ui.modal.closeDialog')"
      :modelValue="showLegacyModal"
      @update:modelValue="val => !val && handleTakeManualControl()"
      :title="$t('terminal.modals.workflowTitle')"
      size="lg"
      :closeOnOverlay="!isProcessingWorkflow"
      class="workflow-step-modal"
    >
      <div class="workflow-step-info" v-if="pendingWorkflowStep">
        <div class="step-counter">
          {{ $t('terminal.modals.stepOf', { step: pendingWorkflowStep.stepNumber, total: pendingWorkflowStep.totalSteps }) }}
        </div>

        <div class="step-description">
          <h4>{{ pendingWorkflowStep.description }}</h4>
          <p>{{ pendingWorkflowStep.explanation || $t('terminal.modals.wantsToExecute') }}</p>
        </div>

        <div class="command-preview">
          <div class="command-label">{{ $t('terminal.modals.commandToExecute') }}</div>
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
            <p><strong>{{ $t('terminal.modals.chooseAction') }}</strong></p>
            <ul>
              <li><strong>{{ $t('terminal.modals.executeOption') }}</strong> {{ $t('terminal.modals.executeDesc') }}</li>
              <li><strong>{{ $t('terminal.modals.skipOption') }}</strong> {{ $t('terminal.modals.skipDesc') }}</li>
              <li><strong>{{ $t('terminal.modals.takeControlOption') }}</strong> {{ $t('terminal.modals.takeControlDesc') }}</li>
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
          {{ (isProcessingWorkflow && lastWorkflowAction === 'execute') ? $t('terminal.modals.executing') : $t('terminal.modals.executeContinue') }}
        </BaseButton>
        <BaseButton
          variant="warning"
          @click="handleSkipWorkflowStep"
          :loading="isProcessingWorkflow && lastWorkflowAction === 'skip'"
          :disabled="isProcessingWorkflow && lastWorkflowAction !== 'skip'"
        >
          {{ (isProcessingWorkflow && lastWorkflowAction === 'skip') ? $t('terminal.modals.skipping') : $t('terminal.modals.skipStep') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          @click="handleTakeManualControl"
          :loading="isProcessingWorkflow && lastWorkflowAction === 'manual'"
          :disabled="isProcessingWorkflow && lastWorkflowAction !== 'manual'"
        >
          {{ (isProcessingWorkflow && lastWorkflowAction === 'manual') ? $t('terminal.modals.takingControl') : $t('terminal.modals.takeManualControl') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { withTimeout } from '@/utils/withTimeout'
import BaseButton from '@/components/base/BaseButton.vue'
import { BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'

const logger = createLogger('TerminalModals')
const { t } = useI18n()

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

/**
 * One of the parent's actions. It may return a value, return a promise, or
 * throw. The modal reports success only once the action has settled
 * successfully, and shows the failure otherwise (#16285).
 */
type ModalAction = () => unknown

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
  reconnectAction: ModalAction
  executeCommandAction: ModalAction
  emergencyKillAction: ModalAction
  confirmStepAction: ModalAction
  skipStepAction: ModalAction
  manualControlAction: ModalAction
}

interface Emits {
  (e: 'hide-reconnect-modal'): void
  (e: 'cancel-command'): void
  (e: 'cancel-kill'): void
}

const props = defineProps<Props>()
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

// Pending auto-hide timers, one per message slot (#16315). A new message in a
// slot cancels that slot's pending timer, so an earlier timer can't blank a
// later message; onBeforeUnmount clears whatever is still pending.
const autoHideTimers = new Map<string, ReturnType<typeof setTimeout>>()

const scheduleAutoHide = (slotKey: string, setter: (msg: string) => void, delayMs: number) => {
  const pending = autoHideTimers.get(slotKey)
  if (pending) clearTimeout(pending)

  autoHideTimers.set(
    slotKey,
    setTimeout(() => {
      setter('')
      autoHideTimers.delete(slotKey)
    }, delayMs),
  )
}

onBeforeUnmount(() => {
  for (const timer of autoHideTimers.values()) clearTimeout(timer)
  autoHideTimers.clear()
})

// Standard error handler
const handleError = (error: unknown, setter: (msg: string) => void, slot: string) => {
  logger.error('Terminal modal error:', error)

  let errorMessage = t('terminal.modals.unexpectedError')

  const err = error as {
    message?: string
    response?: { data?: { detail?: string }; status?: number }
  }

  if (err?.message) {
    errorMessage = err.message
  } else if (err?.response?.data?.detail) {
    errorMessage = err.response!.data!.detail!
  } else if (err?.response?.status === 408) {
    errorMessage = t('terminal.modals.requestTimedOut')
  } else if (err?.response?.status === 500) {
    errorMessage = t('terminal.modals.serverError')
  } else if (err?.response?.status === 404) {
    errorMessage = t('terminal.modals.serviceNotFound')
  } else if (typeof error === 'string') {
    errorMessage = error
  }

  setter(errorMessage)

  // Auto-hide error after 10 seconds
  scheduleAutoHide(`${slot}-error`, setter, 10000)
}

// Standard success handler
const handleSuccess = (message: string, setter: (msg: string) => void, slot: string) => {
  setter(message)

  // Auto-hide success after 5 seconds
  scheduleAutoHide(`${slot}-success`, setter, 5000)
}

interface ActionRun {
  busy: Ref<boolean>
  action: ModalAction
  timeoutMs: number
  timeoutKey: string
  successKey: string
  setError: (msg: string) => void
  setSuccess: (msg: string) => void
  // Auto-hide timer identity (#16315) — distinguishes this run's error/success
  // message slots from the other three action families'.
  slot: string
}

// Runs a parent action against its deadline. A rejection, or a synchronous
// throw, is shown as the error; success is reported only after the action
// settles. withTimeout clears the deadline's timer either way.
const runAction = async (run: ActionRun) => {
  if (run.busy.value) return

  clearMessages()
  run.busy.value = true

  try {
    await withTimeout(Promise.resolve().then(run.action), run.timeoutMs, t(run.timeoutKey))
    handleSuccess(t(run.successKey), run.setSuccess, run.slot)
  } catch (error) {
    handleError(error, run.setError, run.slot)
  } finally {
    run.busy.value = false
  }
}

const handleReconnect = () =>
  runAction({
    busy: isReconnecting,
    action: props.reconnectAction,
    timeoutMs: RECONNECT_TIMEOUT,
    timeoutKey: 'terminal.modals.reconnectTimedOut',
    successKey: 'terminal.modals.reconnectSucceeded',
    setError: (msg) => (connectionError.value = msg),
    setSuccess: (msg) => (connectionSuccess.value = msg),
    slot: 'connection',
  })

const handleExecuteCommand = () =>
  runAction({
    busy: isExecutingCommand,
    action: props.executeCommandAction,
    timeoutMs: COMMAND_TIMEOUT,
    timeoutKey: 'terminal.modals.commandTimedOut',
    successKey: 'terminal.modals.commandSent',
    setError: (msg) => (commandError.value = msg),
    setSuccess: (msg) => (commandSuccess.value = msg),
    slot: 'command',
  })

const cancelCommand = () => {
  if (isExecutingCommand.value) return
  clearMessages()
  emit('cancel-command')
}

const handleEmergencyKill = () =>
  runAction({
    busy: isKillingProcesses,
    action: props.emergencyKillAction,
    timeoutMs: KILL_TIMEOUT,
    timeoutKey: 'terminal.modals.killTimedOut',
    successKey: 'terminal.modals.killSent',
    setError: (msg) => (killError.value = msg),
    setSuccess: (msg) => (killSuccess.value = msg),
    slot: 'kill',
  })

const cancelKill = () => {
  if (isKillingProcesses.value) return
  clearMessages()
  emit('cancel-kill')
}

// The three workflow-step actions share one busy flag; lastWorkflowAction says
// which button shows the spinner.
const runWorkflowAction = async (
  kind: 'execute' | 'skip' | 'manual',
  action: ModalAction,
  timeoutKey: string,
  successKey: string,
) => {
  if (isProcessingWorkflow.value) return

  lastWorkflowAction.value = kind
  await runAction({
    busy: isProcessingWorkflow,
    action,
    timeoutMs: WORKFLOW_TIMEOUT,
    timeoutKey,
    successKey,
    setError: (msg) => (workflowError.value = msg),
    setSuccess: (msg) => (workflowSuccess.value = msg),
    slot: 'workflow',
  })
  lastWorkflowAction.value = null
}

const handleConfirmWorkflowStep = () =>
  runWorkflowAction('execute', props.confirmStepAction, 'terminal.modals.stepTimedOut', 'terminal.modals.stepSent')

const handleSkipWorkflowStep = () =>
  runWorkflowAction('skip', props.skipStepAction, 'terminal.modals.skipTimedOut', 'terminal.modals.stepSkipped')

const handleTakeManualControl = () =>
  runWorkflowAction(
    'manual',
    props.manualControlAction,
    'terminal.modals.manualControlTimedOut',
    'terminal.modals.manualControlTaken',
  )
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
  margin: var(--spacing-0);
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
