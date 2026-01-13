<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="session-control-panel">
    <div class="panel-header">
      <h4>Active Takeover Sessions</h4>
      <button @click="$emit('refresh')" class="btn-icon" :disabled="loading">
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
      </button>
    </div>

    <div v-if="loading && sessions.length === 0" class="loading-state">
      <LoadingSpinner />
      <p>Loading sessions...</p>
    </div>

    <div v-else-if="sessions.length === 0" class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-hand-paper"></i>
      </div>
      <h5>No Active Takeovers</h5>
      <p>No takeover sessions are currently active.</p>
    </div>

    <div v-else class="sessions-grid">
      <div
        v-for="session in sessions"
        :key="session.session_id"
        class="session-card"
        :class="session.status"
      >
        <div class="session-header">
          <div class="session-info">
            <span class="session-operator">{{ session.human_operator }}</span>
            <span class="session-status" :class="session.status">{{ session.status }}</span>
          </div>
          <div class="session-id">
            <code>{{ truncateId(session.session_id) }}</code>
          </div>
        </div>

        <div class="session-body">
          <div class="session-stats">
            <div class="stat">
              <span class="stat-label">Started</span>
              <span class="stat-value">{{ formatTime(session.started_at) }}</span>
            </div>
            <div class="stat" v-if="session.paused_at">
              <span class="stat-label">Paused</span>
              <span class="stat-value">{{ formatTime(session.paused_at) }}</span>
            </div>
            <div class="stat">
              <span class="stat-label">Actions</span>
              <span class="stat-value">{{ session.actions_executed }}</span>
            </div>
          </div>

          <div class="session-scope" v-if="Object.keys(session.takeover_scope).length > 0">
            <span class="scope-label">Scope:</span>
            <pre class="scope-content">{{ JSON.stringify(session.takeover_scope, null, 2) }}</pre>
          </div>
        </div>

        <div class="session-actions">
          <div class="control-buttons">
            <button
              v-if="session.status === 'active'"
              @click="$emit('pause', session.session_id)"
              class="btn-control pause"
              title="Pause Session"
            >
              <i class="fas fa-pause"></i>
            </button>
            <button
              v-if="session.status === 'paused'"
              @click="$emit('resume', session.session_id)"
              class="btn-control resume"
              title="Resume Session"
            >
              <i class="fas fa-play"></i>
            </button>
            <button
              @click="openActionModal(session)"
              class="btn-control action"
              title="Execute Action"
              :disabled="session.status !== 'active'"
            >
              <i class="fas fa-bolt"></i>
            </button>
            <button
              @click="openCompleteModal(session)"
              class="btn-control complete"
              title="Complete Session"
            >
              <i class="fas fa-check"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Action Execution Modal -->
    <BaseModal
      v-model="showActionModal"
      title="Execute Action"
      size="medium"
    >
      <div class="action-form" v-if="selectedSession">
        <p class="info-text">
          Execute an action in takeover session for
          <strong>{{ selectedSession.human_operator }}</strong>
        </p>

        <div class="form-group">
          <label for="action-type">Action Type</label>
          <select id="action-type" v-model="actionForm.action_type">
            <option value="">Select action type...</option>
            <option value="shell_command">Shell Command</option>
            <option value="file_operation">File Operation</option>
            <option value="service_control">Service Control</option>
            <option value="config_change">Configuration Change</option>
            <option value="custom">Custom Action</option>
          </select>
        </div>

        <div class="form-group">
          <label for="action-data">Action Data (JSON)</label>
          <textarea
            id="action-data"
            v-model="actionDataJson"
            rows="5"
            placeholder='{"command": "ls -la", "working_dir": "/tmp"}'
          ></textarea>
          <span class="help-text" v-if="actionDataError">{{ actionDataError }}</span>
        </div>
      </div>

      <template #actions>
        <button @click="showActionModal = false" class="btn-secondary">Cancel</button>
        <button
          @click="handleExecuteAction"
          class="btn-primary"
          :disabled="!isActionValid"
        >
          <i class="fas fa-bolt"></i> Execute
        </button>
      </template>
    </BaseModal>

    <!-- Complete Session Modal -->
    <BaseModal
      v-model="showCompleteModal"
      title="Complete Takeover Session"
      size="medium"
    >
      <div class="complete-form" v-if="selectedSession">
        <p class="info-text">
          Complete the takeover session and return control to the autonomous system.
        </p>

        <div class="form-group">
          <label for="resolution">Resolution Summary</label>
          <textarea
            id="resolution"
            v-model="completeForm.resolution"
            rows="3"
            placeholder="Describe what was done during this takeover session..."
          ></textarea>
        </div>

        <div class="form-group">
          <label for="handback-notes">Handback Notes (Optional)</label>
          <textarea
            id="handback-notes"
            v-model="completeForm.handback_notes"
            rows="2"
            placeholder="Any notes for the autonomous system on resuming operations..."
          ></textarea>
        </div>
      </div>

      <template #actions>
        <button @click="showCompleteModal = false" class="btn-secondary">Cancel</button>
        <button
          @click="handleComplete"
          class="btn-primary"
        >
          <i class="fas fa-check"></i> Complete Session
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type {
  ActiveTakeoverSession,
  TakeoverActionRequest,
  TakeoverCompletionRequest,
} from '@/utils/AdvancedControlApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';

const props = defineProps<{
  sessions: ActiveTakeoverSession[];
  loading: boolean;
}>();

const emit = defineEmits<{
  pause: [sessionId: string];
  resume: [sessionId: string];
  complete: [sessionId: string, completion: TakeoverCompletionRequest];
  'execute-action': [sessionId: string, action: TakeoverActionRequest];
  refresh: [];
}>();

// Modal state
const showActionModal = ref(false);
const showCompleteModal = ref(false);
const selectedSession = ref<ActiveTakeoverSession | null>(null);

// Action form
const actionForm = ref({
  action_type: '',
});
const actionDataJson = ref('{}');
const actionDataError = ref('');

// Complete form
const completeForm = ref<TakeoverCompletionRequest>({
  resolution: '',
  handback_notes: '',
});

const isActionValid = computed(() => {
  if (!actionForm.value.action_type) return false;
  try {
    JSON.parse(actionDataJson.value);
    actionDataError.value = '';
    return true;
  } catch {
    actionDataError.value = 'Invalid JSON format';
    return false;
  }
});

const truncateId = (id: string) => {
  if (id.length <= 12) return id;
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
};

const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString();
};

const openActionModal = (session: ActiveTakeoverSession) => {
  selectedSession.value = session;
  actionForm.value = { action_type: '' };
  actionDataJson.value = '{}';
  actionDataError.value = '';
  showActionModal.value = true;
};

const openCompleteModal = (session: ActiveTakeoverSession) => {
  selectedSession.value = session;
  completeForm.value = { resolution: '', handback_notes: '' };
  showCompleteModal.value = true;
};

const handleExecuteAction = () => {
  if (!selectedSession.value || !isActionValid.value) return;

  const action: TakeoverActionRequest = {
    action_type: actionForm.value.action_type,
    action_data: JSON.parse(actionDataJson.value),
  };

  emit('execute-action', selectedSession.value.session_id, action);
  showActionModal.value = false;
  selectedSession.value = null;
};

const handleComplete = () => {
  if (!selectedSession.value) return;

  emit('complete', selectedSession.value.session_id, completeForm.value);
  showCompleteModal.value = false;
  selectedSession.value = null;
};
</script>

<style scoped>
.session-control-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-icon {
  width: 32px;
  height: 32px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-icon:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-tertiary);
}

.empty-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: var(--bg-tertiary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.empty-state h5 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.sessions-grid {
  padding: 16px;
  display: grid;
  gap: 16px;
}

.session-card {
  background: var(--bg-tertiary);
  border: 2px solid var(--border-default);
  border-radius: 10px;
  overflow: hidden;
}

.session-card.active {
  border-color: var(--color-success);
}

.session-card.paused {
  border-color: var(--color-warning);
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.session-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.session-operator {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.session-status {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.session-status.active {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.session-status.paused {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.session-id code {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--text-muted);
}

.session-body {
  padding: 16px;
}

.session-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.session-scope {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
}

.scope-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.scope-content {
  margin: 0;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 100px;
}

.session-actions {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-default);
}

.control-buttons {
  display: flex;
  gap: 8px;
}

.btn-control {
  width: 36px;
  height: 36px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-control:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-control:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-control.pause:hover:not(:disabled) {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.btn-control.resume:hover:not(:disabled) {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.btn-control.action:hover:not(:disabled) {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.btn-control.complete:hover:not(:disabled) {
  background: var(--color-success-bg);
  color: var(--color-success);
}

/* Modal styles */
.action-form,
.complete-form {
  padding: 8px 0;
}

.info-text {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
}

.info-text strong {
  color: var(--text-primary);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.form-group select,
.form-group textarea {
  width: 100%;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary);
  transition: border-color 0.2s;
}

.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
  font-family: var(--font-mono);
}

.help-text {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-error);
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
