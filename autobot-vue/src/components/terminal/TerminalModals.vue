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
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="$emit('hide-reconnect-modal')">
            Cancel
          </button>
          <button class="btn btn-primary" @click="$emit('reconnect')">
            Reconnect
          </button>
        </div>
      </div>
    </div>

    <!-- Command Confirmation Modal -->
    <div
      v-if="showCommandConfirmation"
      class="confirmation-modal-overlay"
      @click="$emit('cancel-command')"
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
          <button
            class="btn btn-danger"
            @click="$emit('execute-confirmed-command')"
          >
            ⚡ Execute Command
          </button>
          <button
            class="btn btn-secondary"
            @click="$emit('cancel-command')"
          >
            ❌ Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Emergency Kill Confirmation Modal -->
    <div
      v-if="showKillConfirmation"
      class="confirmation-modal-overlay"
      @click="$emit('cancel-kill')"
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
        </div>

        <div class="modal-actions">
          <button
            class="btn btn-danger"
            @click="$emit('confirm-emergency-kill')"
          >
            🛑 KILL ALL PROCESSES
          </button>
          <button
            class="btn btn-secondary"
            @click="$emit('cancel-kill')"
          >
            ❌ Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Legacy Manual Step Confirmation Modal -->
    <div
      v-if="showLegacyModal"
      class="confirmation-modal-overlay"
      @click="$emit('take-manual-control')"
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
          <button
            class="btn btn-success"
            @click="$emit('confirm-workflow-step')"
          >
            ✅ Execute & Continue
          </button>
          <button
            class="btn btn-warning"
            @click="$emit('skip-workflow-step')"
          >
            ⏭️ Skip This Step
          </button>
          <button
            class="btn btn-primary"
            @click="$emit('take-manual-control')"
          >
            👤 Take Manual Control
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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
defineEmits<Emits>()
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

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.btn-primary {
  background-color: #007acc;
  color: white;
}

.btn-primary:hover {
  background-color: #005999;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-danger {
  background-color: #dc3545;
  color: white;
}

.btn-danger:hover {
  background-color: #c82333;
}

.btn-success {
  background-color: #28a745;
  color: white;
  border: 1px solid #1e7e34;
}

.btn-success:hover {
  background-color: #218838;
  border-color: #1c7430;
}

.btn-warning {
  background-color: #ffc107;
  color: #212529;
  border: 1px solid #e0a800;
}

.btn-warning:hover {
  background-color: #e0a800;
  border-color: #d39e00;
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
</style>