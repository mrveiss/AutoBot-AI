<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="takeover-manager">
    <div class="manager-header">
      <h4>Pending Takeover Requests</h4>
      <button @click="$emit('refresh')" class="btn-icon" :disabled="loading">
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
      </button>
    </div>

    <div v-if="loading && requests.length === 0" class="loading-state">
      <LoadingSpinner />
      <p>Loading requests...</p>
    </div>

    <div v-else-if="requests.length === 0" class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-check-circle"></i>
      </div>
      <h5>No Pending Requests</h5>
      <p>All takeover requests have been processed.</p>
    </div>

    <div v-else class="requests-list">
      <div
        v-for="request in requests"
        :key="request.request_id"
        class="request-card"
        :class="request.priority.toLowerCase()"
      >
        <div class="request-header">
          <div class="request-trigger">
            <i :class="getTriggerIcon(request.trigger)"></i>
            <span>{{ formatTrigger(request.trigger) }}</span>
          </div>
          <div class="request-priority" :class="request.priority.toLowerCase()">
            {{ request.priority }}
          </div>
        </div>

        <div class="request-body">
          <p class="request-reason">{{ request.reason }}</p>

          <div class="request-meta">
            <div class="meta-item" v-if="request.requesting_agent">
              <i class="fas fa-robot"></i>
              <span>{{ request.requesting_agent }}</span>
            </div>
            <div class="meta-item">
              <i class="fas fa-clock"></i>
              <span>{{ formatTime(request.created_at) }}</span>
            </div>
            <div class="meta-item" v-if="request.timeout_at">
              <i class="fas fa-hourglass-half"></i>
              <span>Expires: {{ formatTime(request.timeout_at) }}</span>
            </div>
          </div>

          <div class="affected-tasks" v-if="request.affected_tasks?.length">
            <span class="tasks-label">Affected Tasks:</span>
            <div class="tasks-list">
              <span
                v-for="task in request.affected_tasks.slice(0, 3)"
                :key="task"
                class="task-badge"
              >
                {{ task }}
              </span>
              <span
                v-if="request.affected_tasks.length > 3"
                class="task-badge more"
              >
                +{{ request.affected_tasks.length - 3 }} more
              </span>
            </div>
          </div>
        </div>

        <div class="request-actions">
          <button
            @click="openApprovalModal(request)"
            class="btn-approve"
          >
            <i class="fas fa-check"></i> Approve
          </button>
        </div>
      </div>
    </div>

    <!-- Approval Modal -->
    <BaseModal
      v-model="showApprovalModal"
      title="Approve Takeover Request"
      size="medium"
    >
      <div class="approval-form" v-if="selectedRequest">
        <div class="request-summary">
          <div class="summary-row">
            <span class="label">Trigger:</span>
            <span class="value">{{ formatTrigger(selectedRequest.trigger) }}</span>
          </div>
          <div class="summary-row">
            <span class="label">Reason:</span>
            <span class="value">{{ selectedRequest.reason }}</span>
          </div>
          <div class="summary-row">
            <span class="label">Priority:</span>
            <span class="value priority" :class="selectedRequest.priority.toLowerCase()">
              {{ selectedRequest.priority }}
            </span>
          </div>
        </div>

        <div class="form-group">
          <label for="operator-name">Operator Name</label>
          <input
            id="operator-name"
            v-model="approvalForm.human_operator"
            type="text"
            placeholder="Enter your name"
            required
          />
        </div>

        <div class="form-group">
          <label for="scope-notes">Scope Notes (Optional)</label>
          <textarea
            id="scope-notes"
            v-model="scopeNotes"
            rows="3"
            placeholder="Add any notes about the takeover scope..."
          ></textarea>
        </div>
      </div>

      <template #actions>
        <button @click="showApprovalModal = false" class="btn-secondary">Cancel</button>
        <button
          @click="handleApprove"
          class="btn-primary"
          :disabled="!isApprovalValid"
        >
          <i class="fas fa-check"></i> Approve Takeover
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { PendingTakeoverRequest, TakeoverApprovalRequest, TakeoverTrigger } from '@/utils/AdvancedControlApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';

const props = defineProps<{
  requests: PendingTakeoverRequest[];
  loading: boolean;
}>();

const emit = defineEmits<{
  approve: [requestId: string, approval: TakeoverApprovalRequest];
  refresh: [];
}>();

const showApprovalModal = ref(false);
const selectedRequest = ref<PendingTakeoverRequest | null>(null);
const approvalForm = ref<TakeoverApprovalRequest>({
  human_operator: '',
});
const scopeNotes = ref('');

const isApprovalValid = computed(() => {
  return approvalForm.value.human_operator.trim().length > 0;
});

const getTriggerIcon = (trigger: TakeoverTrigger): string => {
  const icons: Record<TakeoverTrigger, string> = {
    MANUAL_REQUEST: 'fas fa-hand-paper',
    CRITICAL_ERROR: 'fas fa-exclamation-triangle',
    SECURITY_CONCERN: 'fas fa-shield-alt',
    USER_INTERVENTION_REQUIRED: 'fas fa-user-clock',
    SYSTEM_OVERLOAD: 'fas fa-server',
    APPROVAL_REQUIRED: 'fas fa-clipboard-check',
    TIMEOUT_EXCEEDED: 'fas fa-clock',
  };
  return icons[trigger] || 'fas fa-question';
};

const formatTrigger = (trigger: TakeoverTrigger): string => {
  return trigger.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
};

const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp);
  return date.toLocaleString();
};

const openApprovalModal = (request: PendingTakeoverRequest) => {
  selectedRequest.value = request;
  approvalForm.value = { human_operator: '' };
  scopeNotes.value = '';
  showApprovalModal.value = true;
};

const handleApprove = () => {
  if (!selectedRequest.value || !isApprovalValid.value) return;

  const approval: TakeoverApprovalRequest = {
    human_operator: approvalForm.value.human_operator.trim(),
  };

  if (scopeNotes.value.trim()) {
    approval.takeover_scope = { notes: scopeNotes.value.trim() };
  }

  emit('approve', selectedRequest.value.request_id, approval);
  showApprovalModal.value = false;
  selectedRequest.value = null;
};
</script>

<style scoped>
.takeover-manager {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.manager-header h4 {
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
  background: var(--color-success-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: var(--color-success);
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

.requests-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.request-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  overflow: hidden;
}

.request-card.critical {
  border-color: var(--color-error);
}

.request-card.high {
  border-color: var(--color-warning);
}

.request-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.request-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.request-trigger i {
  color: var(--color-primary);
}

.request-priority {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.request-priority.low {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.request-priority.medium {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.request-priority.high {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.request-priority.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.request-body {
  padding: 16px;
}

.request-reason {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.request-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.meta-item i {
  width: 14px;
  text-align: center;
}

.affected-tasks {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
}

.tasks-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.tasks-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.task-badge {
  padding: 2px 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

.task-badge.more {
  color: var(--text-muted);
  font-style: italic;
}

.request-actions {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
}

.btn-approve {
  padding: 8px 16px;
  background: var(--color-success);
  color: var(--text-on-success, #fff);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-approve:hover {
  background: var(--color-success-hover, #16a34a);
}

/* Modal styles */
.approval-form {
  padding: 8px 0;
}

.request-summary {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}

.summary-row .label {
  font-size: 13px;
  color: var(--text-muted);
}

.summary-row .value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.summary-row .value.priority.critical {
  color: var(--color-error);
}

.summary-row .value.priority.high {
  color: var(--color-warning);
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

.form-group input,
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

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
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
