<template>
  <div v-if="visible" class="confirmation-modal-overlay" @click="closeModal">
    <div class="advanced-step-modal" @click.stop>
      <!-- Modal Header -->
      <div class="modal-header">
        <h3 class="modal-title">🤖 Advanced Workflow Step Management</h3>
        <button class="close-button" @click="closeModal">×</button>
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
          <button class="edit-command-btn" @click="showCommandEditor = !showCommandEditor">
            📝 Edit
          </button>
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
            <button @click="saveCommandEdit" class="save-btn">💾 Save</button>
            <button @click="cancelCommandEdit" class="cancel-btn">❌ Cancel</button>
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
          <button @click="showStepsManager = !showStepsManager" class="toggle-btn">
            {{ showStepsManager ? '▼ Hide' : '▶ Show' }}
          </button>
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
                <button @click="moveStepUp(index)" :disabled="index === 0" class="step-control">↑</button>
                <button @click="moveStepDown(index)" :disabled="index === workflowSteps.length - 1" class="step-control">↓</button>
                <button @click="deleteStep(index)" :disabled="workflowSteps.length <= 1" class="step-control delete">🗑️</button>
              </div>
              
              <div class="step-info">
                <div class="step-number">{{ index + 1 }}</div>
                <div class="step-details">
                  <div class="step-title">{{ step.description }}</div>
                  <div class="step-command"><code>{{ step.command }}</code></div>
                </div>
              </div>
              
              <div class="step-actions">
                <button @click="editStep(index)" class="edit-step-btn">✏️ Edit</button>
                <button @click="insertStepAfter(index)" class="insert-step-btn">➕ Insert After</button>
              </div>
            </div>
          </div>

          <!-- Add New Step -->
          <div class="add-step-section">
            <button @click="showNewStepForm = !showNewStepForm" class="add-step-btn">
              ➕ Add New Step
            </button>
            
            <div v-if="showNewStepForm" class="new-step-form">
              <div class="form-row">
                <label>Description:</label>
                <input v-model="newStep.description" placeholder="Step description" class="form-input">
              </div>
              <div class="form-row">
                <label>Command:</label>
                <textarea v-model="newStep.command" placeholder="Command to execute" class="form-textarea" rows="2"></textarea>
              </div>
              <div class="form-row">
                <label>Explanation:</label>
                <textarea v-model="newStep.explanation" placeholder="What this step does" class="form-textarea" rows="2"></textarea>
              </div>
              <div class="form-actions">
                <button @click="addNewStep" class="save-btn">💾 Add Step</button>
                <button @click="cancelNewStep" class="cancel-btn">❌ Cancel</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Password Handling Section -->
      <div v-if="requiresPassword" class="password-section">
        <div class="password-warning">
          ⚠️ This command may require password input
        </div>
        <div class="password-options">
          <label>
            <input type="radio" v-model="passwordHandling" value="prompt">
            Prompt for password during execution
          </label>
          <label>
            <input type="radio" v-model="passwordHandling" value="skip">
            Skip this step if password is required
          </label>
          <label>
            <input type="radio" v-model="passwordHandling" value="provide">
            Provide password now (not recommended)
          </label>
        </div>
        <div v-if="passwordHandling === 'provide'" class="password-input">
          <input type="password" v-model="providedPassword" placeholder="Enter password" class="password-field">
          <div class="password-note">⚠️ Password will be sent in plain text</div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="modal-actions">
        <div class="primary-actions">
          <button @click="executeStep" class="execute-btn" :disabled="!canExecute">
            ✅ Execute & Continue
          </button>
          <button @click="skipStep" class="skip-btn">
            ⏭️ Skip This Step
          </button>
          <button @click="takeManualControl" class="manual-btn">
            👤 Take Manual Control
          </button>
        </div>
        
        <div class="secondary-actions">
          <button @click="executeAll" class="execute-all-btn" v-if="workflowSteps.length > 1">
            🚀 Execute All Remaining ({{ workflowSteps.length - currentStepIndex }} steps)
          </button>
          <button @click="saveWorkflow" class="save-workflow-btn">
            💾 Save Workflow as Template
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';

// Props
const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  currentStep: {
    type: Object,
    default: () => ({})
  },
  currentStepIndex: {
    type: Number,
    default: 0
  },
  workflowSteps: {
    type: Array,
    default: () => []
  },
  sessionId: {
    type: String,
    default: ''
  }
});

// Emits
const emit = defineEmits([
  'execute-step',
  'skip-step', 
  'take-manual-control',
  'execute-all',
  'save-workflow',
  'update-workflow',
  'close'
]);

// Reactive data
const showCommandEditor = ref(false);
const editedCommand = ref('');
const showStepsManager = ref(false);
const showNewStepForm = ref(false);
const requiresPassword = ref(false);
const passwordHandling = ref('prompt');
const providedPassword = ref('');

// New step form
const newStep = ref({
  description: '',
  command: '',
  explanation: ''
});

// Computed properties
const totalSteps = computed(() => props.workflowSteps.length);

const riskLevel = computed(() => {
  const command = (editedCommand.value || props.currentStep?.command || '').toLowerCase();
  
  // Critical risk patterns
  if (/rm\s+-rf\s+\/($|\s)|dd\s+if=.*of=\/dev\/[sh]d|mkfs\./.test(command)) {
    return 'critical';
  }
  
  // High risk patterns  
  if (/rm\s+-rf|sudo\s+rm|killall\s+-9|chmod\s+777.*\/$/.test(command)) {
    return 'high';
  }
  
  // Moderate risk patterns
  if (/sudo\s+(apt|yum|dnf).*install|sudo\s+systemctl/.test(command)) {
    return 'moderate';
  }
  
  return 'low';
});

const riskReasons = computed(() => {
  const command = (editedCommand.value || props.currentStep?.command || '').toLowerCase();
  const reasons = [];
  
  if (command.includes('sudo')) {
    reasons.push('Command uses elevated privileges (sudo)');
  }
  if (command.includes('rm ')) {
    reasons.push('Command deletes files or directories');
  }
  if (command.includes('install')) {
    reasons.push('Command installs software packages');
  }
  if (command.includes('systemctl')) {
    reasons.push('Command modifies system services');
  }
  if (command.includes('chmod')) {
    reasons.push('Command changes file permissions');
  }
  
  return reasons;
});

const canExecute = computed(() => {
  return props.currentStep?.command && (!requiresPassword.value || passwordHandling.value !== '');
});

// Methods
const closeModal = () => {
  emit('close');
};

const executeStep = () => {
  const stepData = {
    ...props.currentStep,
    command: editedCommand.value || props.currentStep.command,
    passwordHandling: passwordHandling.value,
    providedPassword: providedPassword.value
  };
  
  emit('execute-step', stepData);
  closeModal();
};

const skipStep = () => {
  emit('skip-step', props.currentStepIndex);
  closeModal();
};

const takeManualControl = () => {
  emit('take-manual-control');
  closeModal();
};

const executeAll = () => {
  emit('execute-all');
  closeModal();
};

const saveWorkflow = () => {
  const workflowData = {
    name: `Custom Workflow ${new Date().toISOString().split('T')[0]}`,
    steps: props.workflowSteps,
    sessionId: props.sessionId
  };
  
  emit('save-workflow', workflowData);
};

const saveCommandEdit = () => {
  showCommandEditor.value = false;
  // Command will be used in executeStep
};

const cancelCommandEdit = () => {
  editedCommand.value = props.currentStep?.command || '';
  showCommandEditor.value = false;
};

const moveStepUp = (index) => {
  if (index > 0) {
    const steps = [...props.workflowSteps];
    [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
    emit('update-workflow', steps);
  }
};

const moveStepDown = (index) => {
  if (index < props.workflowSteps.length - 1) {
    const steps = [...props.workflowSteps];
    [steps[index], steps[index + 1]] = [steps[index + 1], steps[index]];
    emit('update-workflow', steps);
  }
};

const deleteStep = (index) => {
  if (props.workflowSteps.length > 1) {
    const steps = [...props.workflowSteps];
    steps.splice(index, 1);
    emit('update-workflow', steps);
  }
};

const editStep = (index) => {
  // TODO: Open edit dialog for specific step
  console.log('Edit step:', index);
};

const insertStepAfter = (index) => {
  const steps = [...props.workflowSteps];
  const newStepData = {
    id: Date.now(),
    description: 'New Step',
    command: 'echo "New step"',
    explanation: 'Custom inserted step'
  };
  
  steps.splice(index + 1, 0, newStepData);
  emit('update-workflow', steps);
};

const addNewStep = () => {
  if (newStep.value.description && newStep.value.command) {
    const steps = [...props.workflowSteps];
    steps.push({
      id: Date.now(),
      ...newStep.value
    });
    
    emit('update-workflow', steps);
    cancelNewStep();
  }
};

const cancelNewStep = () => {
  newStep.value = {
    description: '',
    command: '',
    explanation: ''
  };
  showNewStepForm.value = false;
};

// Check if command requires password
const checkPasswordRequirement = (command) => {
  const sudoPattern = /sudo\s+(?!echo|ls|pwd|whoami|date|uptime)/;
  const passwordCommands = ['sudo', 'su', 'passwd', 'ssh'];
  
  requiresPassword.value = sudoPattern.test(command) || 
    passwordCommands.some(cmd => command.toLowerCase().includes(cmd));
};

// Watchers
watch(() => props.currentStep?.command, (newCommand) => {
  if (newCommand) {
    editedCommand.value = newCommand;
    checkPasswordRequirement(newCommand);
  }
}, { immediate: true });

watch(() => editedCommand.value, (newCommand) => {
  if (newCommand) {
    checkPasswordRequirement(newCommand);
  }
});
</script>

<style scoped>
.confirmation-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.advanced-step-modal {
  background: #1a1a1a;
  border: 2px solid #333;
  border-radius: 12px;
  min-width: 800px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  color: #ffffff;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #333;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
}

.modal-title {
  margin: 0;
  font-size: 1.3em;
  font-weight: 600;
}

.close-button {
  background: none;
  border: none;
  color: #ffffff;
  font-size: 24px;
  cursor: pointer;
  padding: 5px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-button:hover {
  background: rgba(255, 255, 255, 0.1);
}

.current-step-info {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.step-counter {
  font-size: 0.9em;
  color: #9ca3af;
  margin-bottom: 8px;
}

.step-description {
  font-size: 1.1em;
  margin-bottom: 8px;
}

.step-explanation {
  color: #d1d5db;
  font-size: 0.95em;
}

.command-section {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.section-label {
  display: block;
  font-weight: 600;
  margin-bottom: 12px;
  color: #f3f4f6;
}

.command-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #0f1419;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #374151;
}

.command-preview code {
  flex: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  background: none;
  color: #22c55e;
}

.edit-command-btn {
  background: #374151;
  border: 1px solid #4b5563;
  color: #ffffff;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85em;
  transition: all 0.2s;
}

.edit-command-btn:hover {
  background: #4b5563;
}

.command-editor {
  margin-top: 12px;
  border: 1px solid #374151;
  border-radius: 8px;
  background: #0f1419;
}

.command-input {
  width: 100%;
  background: transparent;
  border: none;
  padding: 12px;
  color: #ffffff;
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
  border-top: 1px solid #374151;
}

.risk-section {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.risk-indicator {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.risk-indicator.low {
  background: rgba(34, 197, 94, 0.1);
  border-color: #22c55e;
}

.risk-indicator.moderate {
  background: rgba(251, 191, 36, 0.1);
  border-color: #fbbf24;
}

.risk-indicator.high {
  background: rgba(249, 115, 22, 0.1);
  border-color: #f97316;
}

.risk-indicator.critical {
  background: rgba(239, 68, 68, 0.1);
  border-color: #ef4444;
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
  color: #d1d5db;
  margin-bottom: 4px;
}

.workflow-management {
  border-bottom: 1px solid #333;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #374151;
}

.section-header h4 {
  margin: 0;
  font-size: 1.1em;
}

.toggle-btn {
  background: #374151;
  border: 1px solid #4b5563;
  color: #ffffff;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85em;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: #4b5563;
}

.steps-manager {
  padding: 20px;
}

.steps-list {
  margin-bottom: 20px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border: 1px solid #374151;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #111827;
  transition: all 0.2s;
}

.step-item.current {
  border-color: #2563eb;
  background: rgba(37, 99, 235, 0.1);
}

.step-item.completed {
  opacity: 0.7;
  border-color: #22c55e;
}

.step-controls {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-control {
  background: #374151;
  border: 1px solid #4b5563;
  color: #ffffff;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8em;
  width: 32px;
  text-align: center;
  transition: all 0.2s;
}

.step-control:hover:not(:disabled) {
  background: #4b5563;
}

.step-control:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.step-control.delete:hover:not(:disabled) {
  background: #dc2626;
  border-color: #dc2626;
}

.step-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #2563eb;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.9em;
}

.step-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
}

.step-details {
  flex: 1;
}

.step-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.step-command {
  font-size: 0.85em;
  color: #9ca3af;
}

.step-command code {
  background: rgba(0, 0, 0, 0.3);
  padding: 2px 6px;
  border-radius: 4px;
  color: #22c55e;
}

.step-actions {
  display: flex;
  gap: 8px;
}

.edit-step-btn,
.insert-step-btn {
  background: #374151;
  border: 1px solid #4b5563;
  color: #ffffff;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8em;
  transition: all 0.2s;
}

.edit-step-btn:hover,
.insert-step-btn:hover {
  background: #4b5563;
}

.add-step-section {
  border-top: 1px solid #374151;
  padding-top: 20px;
}

.add-step-btn {
  background: #059669;
  border: 1px solid #10b981;
  color: #ffffff;
  padding: 12px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
  width: 100%;
}

.add-step-btn:hover {
  background: #047857;
}

.new-step-form {
  margin-top: 16px;
  padding: 20px;
  border: 1px solid #374151;
  border-radius: 8px;
  background: #0f1419;
}

.form-row {
  margin-bottom: 16px;
}

.form-row label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
  color: #f3f4f6;
}

.form-input,
.form-textarea {
  width: 100%;
  background: #111827;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 10px;
  border-radius: 6px;
  font-family: inherit;
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #2563eb;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.password-section {
  padding: 20px;
  border-bottom: 1px solid #333;
  background: rgba(251, 191, 36, 0.05);
}

.password-warning {
  color: #fbbf24;
  font-weight: 600;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.password-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
  background: #111827;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.password-note {
  font-size: 0.85em;
  color: #f97316;
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

.execute-btn,
.skip-btn,
.manual-btn,
.execute-all-btn,
.save-workflow-btn,
.save-btn,
.cancel-btn {
  padding: 12px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-size: 0.95em;
}

.execute-btn {
  background: #22c55e;
  color: #ffffff;
}

.execute-btn:hover:not(:disabled) {
  background: #16a34a;
}

.execute-btn:disabled {
  background: #374151;
  color: #9ca3af;
  cursor: not-allowed;
}

.skip-btn {
  background: #6b7280;
  color: #ffffff;
}

.skip-btn:hover {
  background: #4b5563;
}

.manual-btn {
  background: #2563eb;
  color: #ffffff;
}

.manual-btn:hover {
  background: #1d4ed8;
}

.execute-all-btn {
  background: #7c3aed;
  color: #ffffff;
}

.execute-all-btn:hover {
  background: #6d28d9;
}

.save-workflow-btn {
  background: #059669;
  color: #ffffff;
}

.save-workflow-btn:hover {
  background: #047857;
}

.save-btn {
  background: #22c55e;
  color: #ffffff;
}

.save-btn:hover {
  background: #16a34a;
}

.cancel-btn {
  background: #dc2626;
  color: #ffffff;
}

.cancel-btn:hover {
  background: #b91c1c;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}

/* Responsive design */
@media (max-width: 768px) {
  .advanced-step-modal {
    min-width: 95vw;
    margin: 10px;
  }
  
  .primary-actions,
  .secondary-actions {
    flex-direction: column;
  }
  
  .step-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .step-info {
    width: 100%;
  }
  
  .step-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>