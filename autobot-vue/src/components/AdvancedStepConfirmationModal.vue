<template>
  <div v-if="visible" class="confirmation-modal-overlay" @click="closeModal" tabindex="0" @keyup.enter="handleKeyUp" @keyup.space="handleKeyUp">
    <div class="advanced-step-modal" @click.stop tabindex="0" @keyup.enter="handleModalKeyUp" @keyup.space="handleModalKeyUp">
      <!-- Modal Header -->
      <div class="modal-header">
        <h3 class="modal-title">🤖 Advanced Workflow Step Management</h3>
        <BaseButton variant="ghost" size="xs" @click="closeModal" class="close-button" aria-label="Close modal">×</BaseButton>
      </div>

      <!-- Current Step Info -->
      <div class="current-step-info">
        <div class="step-counter">
          Step {{ currentStepIndex + 1 }} of {{ totalSteps }}
        </div>
        <div class="step-description">
          <strong>{{ currentStep?.description || 'Execute Command' }}</strong>
        </div>
        <div class="step-explanation">
          {{ currentStep?.explanation || 'AI-generated workflow step' }}
        </div>
      </div>

      <!-- Command Preview -->
      <div class="command-section">
        <label class="section-label">Command to Execute:</label>
        <div class="command-preview">
          <code>{{ currentStep?.command }}</code>
          <BaseButton variant="outline" size="xs" @click="showCommandEditor = !showCommandEditor" class="edit-command-btn" aria-label="Edit command">
            📝 Edit
          </BaseButton>
        </div>

        <!-- Command Editor -->
        <div v-if="showCommandEditor" class="command-editor">
          <textarea
            v-model="editedCommand"
            class="command-input"
            rows="3"
            placeholder="Edit the command..."
          ></textarea>
          <div class="editor-actions">
            <BaseButton variant="success" size="sm" @click="saveCommandEdit" aria-label="Save edit">💾 Save</BaseButton>
            <BaseButton variant="secondary" size="sm" @click="cancelCommandEdit" aria-label="Cancel edit">❌ Cancel</BaseButton>
          </div>
        </div>
      </div>

      <!-- Risk Assessment -->
      <div class="risk-section">
        <div class="risk-indicator" :class="riskLevel">
          <span class="risk-label">Risk Level: {{ riskLevel.toUpperCase() }}</span>
          <div class="risk-reasons">
            <div v-for="reason in riskReasons" :key="reason" class="risk-reason">
              • {{ reason }}
            </div>
          </div>
        </div>
      </div>

      <!-- Workflow Steps Management -->
      <div class="workflow-management">
        <div class="section-header">
          <h4>📋 Workflow Steps Management</h4>
          <BaseButton variant="outline" size="sm" @click="showStepsManager = !showStepsManager" :aria-label="showStepsManager ? '▼ Hide Steps' : '▶ Show Steps'">
            {{ showStepsManager ? '▼ Hide' : '▶ Show' }}
          </BaseButton>
        </div>

        <div v-if="showStepsManager" class="steps-manager">
          <!-- Steps List -->
          <div class="steps-list">
            <div
              v-for="(step, index) in workflowSteps"
              :key="step.id || index"
              class="step-item"
              :class="{ 'current': index === currentStepIndex, 'completed': index < currentStepIndex }"
            >
              <div class="step-controls">
                <BaseButton variant="outline" size="xs" @click="moveStepUp(index)" :disabled="index === 0" aria-label="Move step up">↑</BaseButton>
                <BaseButton variant="outline" size="xs" @click="moveStepDown(index)" :disabled="index === workflowSteps.length - 1" aria-label="Move step down">↓</BaseButton>
                <BaseButton variant="danger" size="xs" @click="deleteStep(index)" :disabled="workflowSteps.length <= 1" aria-label="Delete step">🗑️</BaseButton>
              </div>

              <div class="step-info">
                <div class="step-number">{{ index + 1 }}</div>
                <div class="step-details">
                  <div class="step-title">{{ step.description }}</div>
                  <div class="step-command"><code>{{ step.command }}</code></div>
                </div>
              </div>

              <div class="step-actions">
                <BaseButton variant="outline" size="xs" @click="editStep(index)" aria-label="Edit step">✏️ Edit</BaseButton>
                <BaseButton variant="success" size="xs" @click="insertStepAfter(index)" aria-label="Insert step after">➕ Insert After</BaseButton>
              </div>
            </div>
          </div>

          <!-- Add New Step -->
          <div class="add-step-section">
            <BaseButton variant="success" @click="showAddStepForm = !showAddStepForm" class="add-step-btn" aria-label="Add new step">
              ➕ Add New Step
            </BaseButton>

            <div v-if="showAddStepForm" class="add-step-form">
              <div class="form-field">
                <label>Description:</label>
                <input
                  v-model="newStep.description"
                  type="text"
                  class="form-input"
                  placeholder="Enter step description..."
                />
              </div>

              <div class="form-field">
                <label>Command:</label>
                <textarea
                  v-model="newStep.command"
                  class="form-textarea"
                  rows="2"
                  placeholder="Enter command to execute..."
                ></textarea>
              </div>

              <div class="form-field">
                <label>Explanation (optional):</label>
                <textarea
                  v-model="newStep.explanation"
                  class="form-textarea"
                  rows="2"
                  placeholder="Explain what this step does..."
                ></textarea>
              </div>

              <div class="form-actions">
                <BaseButton variant="success" @click="addNewStep" aria-label="Add step">✅ Add Step</BaseButton>
                <BaseButton variant="secondary" @click="cancelAddStep" aria-label="Cancel">❌ Cancel</BaseButton>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Advanced Options -->
      <div class="advanced-options" v-if="showAdvancedOptions">
        <h4>⚙️ Advanced Options</h4>

        <!-- Automatic Execution -->
        <div class="option-group">
          <label>
            <input
              type="checkbox"
              v-model="enableAutoExecution"
              @change="onAutoExecutionChange"
            />
            🔄 Automatic execution of remaining steps
          </label>
        </div>

        <!-- Timeout Settings -->
        <div class="option-group">
          <label>⏱️ Execution timeout (seconds):</label>
          <input
            type="number"
            v-model="executionTimeout"
            min="5"
            max="300"
            class="timeout-input"
          />
        </div>

        <!-- Password Protection -->
        <div class="option-group">
          <label>🔐 Password protection for destructive commands:</label>
          <div class="password-options">
            <label>
              <input
                type="radio"
                v-model="passwordProtection"
                value="none"
              />
              None
            </label>
            <label>
              <input
                type="radio"
                v-model="passwordProtection"
                value="required"
              />
              Required
            </label>
            <label>
              <input
                type="radio"
                v-model="passwordProtection"
                value="optional"
              />
              Optional
            </label>
          </div>

          <div v-if="passwordProtection !== 'none'" class="password-input">
            <input
              type="password"
              v-model="adminPassword"
              placeholder="Enter admin password..."
              class="password-field"
            />
            <div class="password-note">Required for executing high-risk commands</div>
          </div>
        </div>
      </div>

      <!-- Edit Dialog Overlay -->
      <div v-if="showEditDialog" class="edit-overlay" @click="cancelEdit">
        <div class="edit-dialog" @click.stop>
          <div class="edit-header">
            <h4>✏️ Edit Step {{ editingStepIndex + 1 }}</h4>
            <BaseButton variant="ghost" size="xs" @click="cancelEdit" class="close-button" aria-label="Close dialog">×</BaseButton>
          </div>

          <div class="edit-content">
            <!-- Error Display -->
            <div v-if="editError" class="error-message">
              <div class="error-icon">⚠️</div>
              <div class="error-text">{{ editError }}</div>
            </div>

            <!-- Success Display -->
            <div v-if="editSuccess" class="success-message">
              <div class="success-icon">✅</div>
              <div class="success-text">{{ editSuccess }}</div>
            </div>

            <div class="form-field">
              <label for="edit-description">Description:</label>
              <input
                id="edit-description"
                ref="editDescriptionInput"
                v-model="editingStep.description"
                type="text"
                class="form-input"
                placeholder="Enter step description..."
                @input="validateEditForm"
              />
              <div v-if="validationErrors.description" class="field-error">{{ validationErrors.description }}</div>
            </div>

            <div class="form-field">
              <label for="edit-command">Command:</label>
              <textarea
                id="edit-command"
                v-model="editingStep.command"
                class="form-textarea"
                rows="3"
                placeholder="Enter command to execute..."
                @input="validateEditForm"
              ></textarea>
              <div v-if="validationErrors.command" class="field-error">{{ validationErrors.command }}</div>
            </div>

            <div class="form-field">
              <label for="edit-explanation">Explanation (optional):</label>
              <textarea
                id="edit-explanation"
                v-model="editingStep.explanation"
                class="form-textarea"
                rows="2"
                placeholder="Explain what this step does..."
                @input="validateEditForm"
              ></textarea>
            </div>

            <!-- Live Risk Assessment -->
            <div class="edit-risk-section">
              <div class="edit-risk-indicator" :class="editRiskLevel">
                <span class="risk-label">Live Risk Assessment: {{ editRiskLevel.toUpperCase() }}</span>
                <div class="risk-reasons">
                  <div v-for="reason in editRiskReasons" :key="reason" class="risk-reason">
                    • {{ reason }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="edit-actions">
            <BaseButton
              variant="success"
              @click="saveEdit"
              :disabled="!isEditFormValid || isSavingEdit"
              :loading="isSavingEdit"
              aria-label="Save changes"
            >
              💾 {{ isSavingEdit ? 'Saving...' : 'Save Changes' }}
            </BaseButton>
            <BaseButton variant="secondary" @click="cancelEdit" :disabled="isSavingEdit" aria-label="Cancel">❌ Cancel</BaseButton>
          </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="modal-actions">
        <div class="primary-actions">
          <BaseButton variant="success" @click="executeStep" :disabled="!currentStep" class="execute-btn" aria-label="Execute this step">
            ✅ Execute This Step
          </BaseButton>
          <BaseButton variant="secondary" @click="skipStep" class="skip-btn" aria-label="Skip this step">
            ⏭️ Skip This Step
          </BaseButton>
          <BaseButton variant="primary" @click="takeManualControl" class="manual-btn" aria-label="Take manual control">
            👤 Take Manual Control
          </BaseButton>
        </div>

        <div class="secondary-actions">
          <BaseButton variant="info" @click="executeAllRemaining" class="execute-all-btn" aria-label="Execute all remaining steps">
            🚀 Execute All Remaining
          </BaseButton>
          <BaseButton variant="success" @click="saveWorkflow" class="save-workflow-btn" aria-label="Save workflow">
            💾 Save Workflow
          </BaseButton>
          <BaseButton variant="secondary" @click="toggleAdvancedOptions" class="toggle-advanced-btn" aria-label="Toggle advanced options">
            ⚙️ {{ showAdvancedOptions ? 'Hide' : 'Show' }} Advanced
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'

const logger = createLogger('AdvancedStepConfirmationModal')

// Interfaces
interface WorkflowStep {
  id?: string
  description: string
  command: string
  explanation?: string
  status?: 'pending' | 'executing' | 'completed' | 'failed' | 'skipped'
}

interface Props {
  visible: boolean
  workflowSteps: WorkflowStep[]
  currentStepIndex: number
  showAdvancedOptions?: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'execute-step'): void
  (e: 'skip-step'): void
  (e: 'manual-control'): void
  (e: 'execute-all'): void
  (e: 'save-workflow'): void
  (e: 'update-steps', steps: WorkflowStep[]): void
}

// Props and emits
const props = withDefaults(defineProps<Props>(), {
  showAdvancedOptions: false
})

const emit = defineEmits<Emits>()

// Reactive data
const showStepsManager = ref(false)
const showAddStepForm = ref(false)
const showCommandEditor = ref(false)
const showAdvancedOptions = ref(props.showAdvancedOptions)

// Advanced options
const enableAutoExecution = ref(false)
const executionTimeout = ref(30)
const passwordProtection = ref('none')
const adminPassword = ref('')

// Edit functionality
const showEditDialog = ref(false)
const editingStepIndex = ref(-1)
const editingStep = ref({ description: '', command: '', explanation: '' })
const editDescriptionInput = ref<HTMLInputElement | null>(null)
const isSavingEdit = ref(false)
const editError = ref('')
const editSuccess = ref('')
const isEditFormValid = ref(false)
const validationErrors = ref<Record<string, string>>({})

// New step form
const newStep = ref({ description: '', command: '', explanation: '' })

// Command editing
const editedCommand = ref('')

// Computed properties
const currentStep = computed(() => props.workflowSteps[props.currentStepIndex])
const totalSteps = computed(() => props.workflowSteps.length)

// Risk assessment for current step
const riskLevel = computed(() => {
  if (!currentStep.value?.command) return 'low'
  const command = currentStep.value.command.toLowerCase()

  if (command.includes('rm -rf') || command.includes('format') || command.includes('delete')) return 'critical'
  if (command.includes('sudo') || command.includes('chmod 777') || command.includes('chown')) return 'high'
  if (command.includes('install') || command.includes('update') || command.includes('modify')) return 'moderate'

  return 'low'
})

const riskReasons = computed(() => {
  if (!currentStep.value?.command) return []
  const command = currentStep.value.command.toLowerCase()
  const reasons = []

  if (command.includes('rm -rf')) reasons.push('Recursive file deletion detected')
  if (command.includes('sudo')) reasons.push('Administrative privileges required')
  if (command.includes('chmod 777')) reasons.push('Permissive file permissions')
  if (command.includes('install')) reasons.push('Software installation/modification')
  if (command.includes('format')) reasons.push('Disk formatting operation')

  return reasons
})

// Edit step risk assessment
const editRiskLevel = computed(() => {
  if (!editingStep.value?.command) return 'low'
  const command = editingStep.value.command.toLowerCase()

  if (command.includes('rm -rf') || command.includes('format') || command.includes('delete')) return 'critical'
  if (command.includes('sudo') || command.includes('chmod 777') || command.includes('chown')) return 'high'
  if (command.includes('install') || command.includes('update') || command.includes('modify')) return 'moderate'

  return 'low'
})

const editRiskReasons = computed(() => {
  if (!editingStep.value?.command) return []
  const command = editingStep.value.command.toLowerCase()
  const reasons = []

  if (command.includes('rm -rf')) reasons.push('Recursive file deletion detected')
  if (command.includes('sudo')) reasons.push('Administrative privileges required')
  if (command.includes('chmod 777')) reasons.push('Permissive file permissions')
  if (command.includes('install')) reasons.push('Software installation/modification')
  if (command.includes('format')) reasons.push('Disk formatting operation')

  return reasons
})

// Watchers
watch(() => props.workflowSteps, () => {
  // Update local state when props change
}, { deep: true })

watch(() => currentStep.value?.command, (newCommand) => {
  if (newCommand) {
    editedCommand.value = newCommand
  }
}, { immediate: true })

// Methods
const closeModal = () => {
  clearMessages()
  emit('close')
}

const clearMessages = () => {
  editError.value = ''
  editSuccess.value = ''
}

const executeStep = () => {
  clearMessages()
  emit('execute-step')
}

const skipStep = () => {
  clearMessages()
  emit('skip-step')
}

const takeManualControl = () => {
  clearMessages()
  emit('manual-control')
}

const executeAllRemaining = () => {
  clearMessages()
  emit('execute-all')
}

const saveWorkflow = () => {
  clearMessages()
  emit('save-workflow')
}

const toggleAdvancedOptions = () => {
  showAdvancedOptions.value = !showAdvancedOptions.value
}

// Step management
const moveStepUp = (index: number) => {
  if (index > 0) {
    const steps = [...props.workflowSteps]
    ;[steps[index - 1], steps[index]] = [steps[index], steps[index - 1]]
    emit('update-steps', steps)
  }
}

const moveStepDown = (index: number) => {
  if (index < props.workflowSteps.length - 1) {
    const steps = [...props.workflowSteps]
    ;[steps[index], steps[index + 1]] = [steps[index + 1], steps[index]]
    emit('update-steps', steps)
  }
}

const deleteStep = (index: number) => {
  if (props.workflowSteps.length > 1) {
    const steps = [...props.workflowSteps]
    steps.splice(index, 1)
    emit('update-steps', steps)
  }
}

const insertStepAfter = (index: number) => {
  const newEmptyStep: WorkflowStep = {
    description: 'New Step',
    command: '',
    explanation: ''
  }
  const steps = [...props.workflowSteps]
  steps.splice(index + 1, 0, newEmptyStep)
  emit('update-steps', steps)
}

// Edit step functionality
const editStep = async (index: number) => {
  const step = props.workflowSteps[index]
  if (!step) return

  clearMessages()
  editingStepIndex.value = index
  editingStep.value = {
    description: step.description || '',
    command: step.command || '',
    explanation: step.explanation || ''
  }
  showEditDialog.value = true

  await nextTick()
  if (editDescriptionInput.value) {
    editDescriptionInput.value.focus()
  }
}

const validateEditForm = () => {
  validationErrors.value = {}

  if (!editingStep.value.description.trim()) {
    validationErrors.value.description = 'Description is required'
  }

  if (!editingStep.value.command.trim()) {
    validationErrors.value.command = 'Command is required'
  }

  isEditFormValid.value = Object.keys(validationErrors.value).length === 0
}

const saveEdit = async () => {
  if (!isEditFormValid.value) return

  clearMessages()
  isSavingEdit.value = true

  try {
    // Simulate save operation with timeout
    const savePromise = new Promise<void>((resolve) => {
      setTimeout(() => {
        const steps = [...props.workflowSteps]
        steps[editingStepIndex.value] = { ...editingStep.value }
        emit('update-steps', steps)
        resolve()
      }, 1000)
    })

    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Save operation timed out')), 10000)
    })

    await Promise.race([savePromise, timeoutPromise])

    editSuccess.value = 'Step updated successfully'
    setTimeout(() => {
      showEditDialog.value = false
      clearMessages()
    }, 1500)

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Failed to save step'
    editError.value = errorMessage
    logger.error('Edit save error:', error)
  } finally {
    isSavingEdit.value = false
  }
}

const cancelEdit = () => {
  if (isSavingEdit.value) return

  clearMessages()
  showEditDialog.value = false
  editingStepIndex.value = -1
  editingStep.value = { description: '', command: '', explanation: '' }
  validationErrors.value = {}
}

// New step functionality
const addNewStep = () => {
  if (!newStep.value.description.trim() || !newStep.value.command.trim()) return

  const steps = [...props.workflowSteps, { ...newStep.value }]
  emit('update-steps', steps)

  newStep.value = { description: '', command: '', explanation: '' }
  showAddStepForm.value = false
}

const cancelAddStep = () => {
  newStep.value = { description: '', command: '', explanation: '' }
  showAddStepForm.value = false
}

// Command editing
const saveCommandEdit = () => {
  if (currentStep.value && editedCommand.value.trim()) {
    const steps = [...props.workflowSteps]
    steps[props.currentStepIndex] = {
      ...currentStep.value,
      command: editedCommand.value.trim()
    }
    emit('update-steps', steps)
    showCommandEditor.value = false
  }
}

const cancelCommandEdit = () => {
  editedCommand.value = currentStep.value?.command || ''
  showCommandEditor.value = false
}

// Advanced options
const onAutoExecutionChange = () => {
  // Handle auto execution change
}

// Event handlers for keyboard navigation
const handleKeyUp = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  if (target && typeof target.click === 'function') {
    target.click()
  }
}

const handleModalKeyUp = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  if (target && typeof target.click === 'function') {
    target.click()
  }
}

// Initialize validation on mount
validateEditForm()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.confirmation-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(3px);
}

.advanced-step-modal {
  background: var(--bg-card);
  border: 2px solid var(--border-secondary);
  border-radius: 12px;
  min-width: 800px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  color: var(--text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-info-dark) 100%);
}

.modal-title {
  color: var(--text-on-primary);
  margin: 0;
  font-size: 1.25em;
  font-weight: 700;
}

.current-step-info {
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
  background: var(--bg-primary);
}

.step-counter {
  display: inline-block;
  background: var(--color-primary);
  color: var(--text-on-primary);
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 0.9em;
  margin-bottom: 8px;
}

.step-description {
  font-size: 1.1em;
  margin-bottom: 8px;
}

.step-explanation {
  color: var(--text-secondary);
  font-size: 0.95em;
}

.command-section {
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
}

.section-label {
  display: block;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.command-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-primary);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.command-preview code {
  flex: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  background: none;
  color: var(--color-success);
}

.command-editor {
  margin-top: 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-primary);
}

.command-input {
  width: 100%;
  background: transparent;
  border: none;
  padding: 12px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  resize: vertical;
}

.command-input:focus {
  outline: none;
}

.editor-actions {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--border-default);
}

.risk-section {
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
}

.risk-indicator,
.edit-risk-indicator {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.risk-indicator.low,
.edit-risk-indicator.low {
  background: var(--color-success-alpha-10);
  border-left-color: var(--color-success);
}

.risk-indicator.moderate,
.edit-risk-indicator.moderate {
  background: var(--color-warning-alpha-10);
  border-left-color: var(--color-warning);
}

.risk-indicator.high,
.edit-risk-indicator.high {
  background: var(--color-error-alpha-10);
  border-left-color: var(--color-error);
}

.risk-indicator.critical,
.edit-risk-indicator.critical {
  background: var(--color-danger-alpha-10);
  border-left-color: var(--color-danger);
  animation: pulse 2s infinite;
}

.risk-label {
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
}

.risk-reasons {
  margin-top: 8px;
}

.risk-reason {
  font-size: 0.9em;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.workflow-management {
  border-bottom: 1px solid var(--border-secondary);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
}

.section-header h4 {
  margin: 0;
  color: var(--text-primary);
}

.steps-manager {
  padding: 0 20px 20px;
}

.steps-list {
  margin-bottom: 20px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.step-item.current {
  border-color: var(--color-primary);
  background: var(--color-primary-alpha-10);
}

.step-item.completed {
  border-color: var(--color-success);
  background: var(--color-success-alpha-10);
}

.step-controls {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
}

.step-number {
  background: var(--color-primary);
  color: var(--text-on-primary);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.9em;
}

.step-details {
  flex: 1;
}

.step-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.step-command {
  font-size: 0.85em;
  color: var(--text-muted);
}

.step-command code {
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.step-actions {
  display: flex;
  gap: 8px;
}

.add-step-section {
  border-top: 1px solid var(--border-default);
  padding-top: 20px;
}

.add-step-form {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.form-field {
  margin-bottom: 16px;
}

.form-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-input,
.form-textarea {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: 10px;
  border-radius: 6px;
  font-family: inherit;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-actions {
  display: flex;
  gap: 12px;
}

.advanced-options {
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
}

.advanced-options h4 {
  margin: 0 0 16px 0;
  color: var(--text-primary);
}

.option-group {
  margin-bottom: 16px;
}

.option-group label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.timeout-input {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  width: 120px;
}

.password-options {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.password-options label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.password-input {
  margin-top: 16px;
}

.password-field {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.password-note {
  font-size: 0.85em;
  color: var(--color-warning);
}

.modal-actions {
  padding: 20px;
}

.primary-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.secondary-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* Edit Dialog */
.edit-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.edit-dialog {
  background: var(--bg-card);
  border: 2px solid var(--border-secondary);
  border-radius: 12px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  color: var(--text-primary);
}

.edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border-secondary);
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
}

.edit-header h4 {
  margin: 0;
  color: var(--text-on-primary);
  font-size: 1.1em;
}

.edit-content {
  padding: 20px;
}

.edit-risk-section {
  margin-top: 16px;
}

.edit-actions {
  display: flex;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid var(--border-secondary);
  justify-content: flex-end;
}

/* Loading spinner */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top: 2px solid currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
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
  background-color: var(--color-error-alpha-10);
  border: 1px solid var(--color-error-alpha-30, rgba(239, 68, 68, 0.3));
  color: var(--color-error);
}

.success-message {
  background-color: var(--color-success-alpha-10);
  border: 1px solid var(--color-success-alpha-30, rgba(34, 197, 94, 0.3));
  color: var(--color-success);
}

.error-icon, .success-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.error-text, .success-text {
  flex: 1;
  word-break: break-word;
}

.field-error {
  color: var(--color-error);
  font-size: 0.85em;
  margin-top: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}

/* Enhanced Mobile Responsive Design */
@media (max-width: 1024px) {
  .advanced-step-modal {
    min-width: 95vw;
    max-width: 95vw;
    margin: 20px 10px;
  }

  .edit-dialog {
    width: 95vw;
    margin: 20px 10px;
  }

  .step-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .step-info {
    width: 100%;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .step-details {
    width: 100%;
  }

  .step-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .advanced-step-modal {
    min-width: 100vw;
    max-width: 100vw;
    margin: 0;
    border-radius: 0;
    max-height: 100vh;
  }

  .edit-dialog {
    width: 100vw;
    max-width: 100vw;
    margin: 0;
    border-radius: 0;
    max-height: 100vh;
  }

  .modal-header,
  .edit-header {
    padding: 16px;
  }

  .modal-title,
  .edit-header h4 {
    font-size: 1.1em;
  }

  .current-step-info,
  .command-section,
  .risk-section,
  .section-header,
  .steps-manager,
  .advanced-options,
  .modal-actions,
  .edit-content {
    padding: 16px;
  }

  .primary-actions,
  .secondary-actions {
    flex-direction: column;
    gap: 8px;
  }


  .step-item {
    padding: 12px;
  }

  .step-controls {
    flex-direction: row;
    gap: 6px;
    order: 3;
    width: 100%;
    justify-content: flex-start;
  }

  .step-info {
    order: 1;
    margin-bottom: 8px;
  }

  .step-actions {
    order: 2;
    margin-bottom: 8px;
  }

  .command-preview {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .password-options {
    flex-direction: column;
    gap: 8px;
  }

  .form-actions,
  .edit-actions {
    flex-direction: column;
    gap: 8px;
  }

  .timeout-input {
    width: 100%;
    max-width: 200px;
  }
}

@media (max-width: 480px) {
  .modal-header,
  .edit-header {
    padding: 12px;
  }

  .current-step-info,
  .command-section,
  .risk-section,
  .section-header,
  .steps-manager,
  .advanced-options,
  .modal-actions,
  .edit-content {
    padding: 12px;
  }

  .modal-title,
  .edit-header h4 {
    font-size: 1em;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .toggle-btn {
    align-self: flex-end;
  }

  .step-number {
    width: 28px;
    height: 28px;
    font-size: 0.8em;
  }

  .step-title {
    font-size: 0.9em;
  }

  .step-command {
    font-size: 0.8em;
  }

  .form-input,
  .form-textarea,
  .password-field {
    font-size: 16px; /* Prevents zoom on iOS */
  }
}

/* Landscape mobile orientation */
@media (max-width: 768px) and (orientation: landscape) {
  .advanced-step-modal,
  .edit-dialog {
    max-height: 100vh;
    overflow-y: auto;
  }

  .primary-actions,
  .secondary-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }

}

</style>
