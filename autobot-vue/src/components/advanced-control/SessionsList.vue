<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="sessions-list">
    <div class="list-header">
      <h4>Active Desktop Streaming Sessions</h4>
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
        <i class="fas fa-desktop"></i>
      </div>
      <h5>No Active Sessions</h5>
      <p>No desktop streaming sessions are currently active.</p>
    </div>

    <div v-else class="sessions-table">
      <table>
        <thead>
          <tr>
            <th>Session ID</th>
            <th>User</th>
            <th>Display</th>
            <th>VNC Port</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="session in sessions" :key="session.session_id">
            <td class="session-id">
              <code>{{ truncateId(session.session_id) }}</code>
            </td>
            <td>{{ session.user_id }}</td>
            <td>{{ session.display }}</td>
            <td>
              <span class="port-badge">{{ session.vnc_port }}</span>
              <span v-if="session.novnc_port" class="port-badge novnc">
                noVNC: {{ session.novnc_port }}
              </span>
            </td>
            <td>
              <span class="status-badge" :class="session.status">
                {{ session.status }}
              </span>
            </td>
            <td class="actions">
              <button
                @click="openVNC(session)"
                class="btn-action"
                title="Open VNC Viewer"
                :disabled="!session.novnc_port"
              >
                <i class="fas fa-external-link-alt"></i>
              </button>
              <button
                @click="confirmTerminate(session)"
                class="btn-action danger"
                title="Terminate Session"
              >
                <i class="fas fa-times"></i>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Terminate Confirmation Modal -->
    <BaseModal
      v-model="showTerminateModal"
      title="Terminate Session"
      size="small"
    >
      <p>
        Are you sure you want to terminate session
        <code>{{ selectedSession?.session_id }}</code>?
      </p>
      <p class="warning-text">
        This will disconnect the user from the desktop streaming session.
      </p>
      <template #actions>
        <button @click="showTerminateModal = false" class="btn-secondary">Cancel</button>
        <button @click="handleTerminate" class="btn-danger">
          <i class="fas fa-times"></i> Terminate
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { getConfig } from '@/config/ssot-config';
import type { StreamingSession } from '@/utils/AdvancedControlApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';

const props = defineProps<{
  sessions: StreamingSession[];
  loading: boolean;
}>();

const emit = defineEmits<{
  terminate: [sessionId: string];
  refresh: [];
}>();

const showTerminateModal = ref(false);
const selectedSession = ref<StreamingSession | null>(null);

const truncateId = (id: string) => {
  if (id.length <= 12) return id;
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
};

const openVNC = (session: StreamingSession) => {
  if (session.novnc_port) {
    const cfg = getConfig();
    const vncUrl = `${cfg.httpProtocol}://${cfg.vm.main}:${session.novnc_port}/vnc.html`;
    window.open(vncUrl, '_blank');
  }
};

const confirmTerminate = (session: StreamingSession) => {
  selectedSession.value = session;
  showTerminateModal.value = true;
};

const handleTerminate = () => {
  if (selectedSession.value) {
    emit('terminate', selectedSession.value.session_id);
    showTerminateModal.value = false;
    selectedSession.value = null;
  }
};
</script>

<style scoped>
.sessions-list {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.list-header h4 {
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

.sessions-table {
  overflow-x: auto;
}

.sessions-table table {
  width: 100%;
  border-collapse: collapse;
}

.sessions-table th,
.sessions-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-default);
}

.sessions-table th {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}

.sessions-table td {
  font-size: 14px;
  color: var(--text-secondary);
}

.session-id code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.port-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  margin-right: 4px;
}

.port-badge.novnc {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: capitalize;
}

.status-badge.active {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.paused {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge.terminated {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.actions {
  display: flex;
  gap: 8px;
}

.btn-action {
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

.btn-action:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-action.danger:hover:not(:disabled) {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.warning-text {
  color: var(--color-warning);
  font-size: 13px;
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

.btn-danger {
  padding: 10px 20px;
  background: var(--color-error);
  color: var(--text-on-error);
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

.btn-danger:hover {
  background: var(--color-error-hover, #b91c1c);
}
</style>
