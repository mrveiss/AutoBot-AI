<template>
  <div class="approval-gate-panel">
    <div class="panel-header">
      <h2 class="panel-title">
        <i class="fas fa-shield-check" aria-hidden="true"></i>
        {{ $t('workflow.approvalGates.title', 'Approval Gates') }}
      </h2>
      <span v-if="pendingCount > 0" class="pending-badge">
        {{ pendingCount }}
      </span>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <select v-model="statusFilter" class="filter-select" @change="refresh">
        <option value="">{{ $t('workflow.approvalGates.allStatuses', 'All Statuses') }}</option>
        <option value="pending">{{ $t('workflow.approvalGates.pending', 'Pending') }}</option>
        <option value="approved">{{ $t('workflow.approvalGates.approved', 'Approved') }}</option>
        <option value="rejected">{{ $t('workflow.approvalGates.rejected', 'Rejected') }}</option>
        <option value="revision_requested">{{ $t('workflow.approvalGates.revisionRequested', 'Revision Requested') }}</option>
      </select>
      <select v-model="typeFilter" class="filter-select" @change="refresh">
        <option value="">{{ $t('workflow.approvalGates.allTypes', 'All Types') }}</option>
        <option value="destructive_action">{{ $t('workflow.approvalGates.destructiveAction', 'Destructive Action') }}</option>
        <option value="resource_request">{{ $t('workflow.approvalGates.resourceRequest', 'Resource Request') }}</option>
        <option value="create_agent">{{ $t('workflow.approvalGates.createAgent', 'Create Agent') }}</option>
        <option value="workflow_gate">{{ $t('workflow.approvalGates.workflowGate', 'Workflow Gate') }}</option>
      </select>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
      <span>{{ $t('common.loading', 'Loading...') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="approvals.length === 0" class="empty-state">
      <i class="fas fa-check-circle" aria-hidden="true"></i>
      <span>{{ $t('workflow.approvalGates.noApprovals', 'No approval gates found') }}</span>
    </div>

    <!-- Approval cards -->
    <div v-else class="approval-list">
      <div
        v-for="approval in approvals"
        :key="approval.id"
        class="approval-card"
        :class="'status-' + approval.status"
      >
        <div class="card-header">
          <span class="approval-title">{{ approval.title }}</span>
          <span class="status-badge" :class="'badge-' + approval.status">
            {{ approval.status.replace('_', ' ') }}
          </span>
        </div>

        <div v-if="approval.description" class="card-description">
          {{ approval.description }}
        </div>

        <div class="card-meta">
          <span v-if="approval.approval_type" class="meta-item">
            <i class="fas fa-tag" aria-hidden="true"></i>
            {{ approval.approval_type.replace('_', ' ') }}
          </span>
          <span v-if="approval.requested_by_agent" class="meta-item">
            <i class="fas fa-robot" aria-hidden="true"></i>
            {{ approval.requested_by_agent }}
          </span>
          <span v-if="approval.decided_by_user" class="meta-item">
            <i class="fas fa-user" aria-hidden="true"></i>
            {{ approval.decided_by_user }}
          </span>
          <span v-if="approval.created_at" class="meta-item">
            <i class="fas fa-clock" aria-hidden="true"></i>
            {{ formatDate(approval.created_at) }}
          </span>
        </div>

        <!-- Actions for pending approvals -->
        <div v-if="approval.status === 'pending'" class="card-actions">
          <BaseButton
            variant="success"
            size="sm"
            @click="handleApprove(approval.id)"
            :aria-label="$t('workflow.approvalGates.approve', 'Approve')"
          >
            <i class="fas fa-check" aria-hidden="true"></i>
            {{ $t('workflow.approvalGates.approve', 'Approve') }}
          </BaseButton>
          <BaseButton
            variant="danger"
            size="sm"
            @click="handleReject(approval.id)"
            :aria-label="$t('workflow.approvalGates.reject', 'Reject')"
          >
            <i class="fas fa-times" aria-hidden="true"></i>
            {{ $t('workflow.approvalGates.reject', 'Reject') }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="sm"
            @click="handleRequestRevision(approval.id)"
            :aria-label="$t('workflow.approvalGates.requestRevision', 'Request Revision')"
          >
            <i class="fas fa-undo" aria-hidden="true"></i>
            {{ $t('workflow.approvalGates.requestRevision', 'Request Revision') }}
          </BaseButton>
        </div>

        <!-- Comment input -->
        <div v-if="activeCommentId === approval.id" class="comment-input">
          <textarea
            v-model="commentText"
            class="comment-textarea"
            :placeholder="$t('workflow.approvalGates.addComment', 'Add a comment...')"
            rows="2"
            @keydown.ctrl.enter="submitComment(approval.id)"
            @keydown.meta.enter="submitComment(approval.id)"
          ></textarea>
          <div class="comment-input-actions">
            <BaseButton variant="secondary" size="sm" @click="cancelComment">
              {{ $t('common.cancel', 'Cancel') }}
            </BaseButton>
            <BaseButton
              variant="primary"
              size="sm"
              @click="submitComment(approval.id)"
              :disabled="!commentText.trim()"
            >
              {{ $t('workflow.approvalGates.submit', 'Submit') }}
            </BaseButton>
          </div>
        </div>
        <button
          v-else
          class="add-comment-btn"
          @click="startComment(approval.id)"
        >
          <i class="fas fa-comment" aria-hidden="true"></i>
          {{ $t('workflow.approvalGates.addComment', 'Add Comment') }}
        </button>

        <!-- Comments list -->
        <div v-if="approval.comments.length > 0" class="comments-list">
          <div
            v-for="comment in approval.comments"
            :key="comment.id"
            class="comment-item"
          >
            <div class="comment-header">
              <span class="comment-author">
                <i
                  :class="comment.author_type === 'agent' ? 'fas fa-robot' : 'fas fa-user'"
                  aria-hidden="true"
                ></i>
                {{ comment.author }}
              </span>
              <span v-if="comment.created_at" class="comment-date">
                {{ formatDate(comment.created_at) }}
              </span>
            </div>
            <p class="comment-body">{{ comment.body }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Approval Gate Panel (#1402)
 *
 * Displays and manages workflow approval gates with
 * filtering, actions, and comments.
 */

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import { useApprovalGates } from '@/composables/useApprovalGates'

const { t } = useI18n()

const {
  approvals,
  loading,
  error,
  pendingCount,
  fetchApprovals,
  approve: doApprove,
  reject: doReject,
  requestRevision: doRequestRevision,
  addComment: doAddComment,
} = useApprovalGates()

// Filters
const statusFilter = ref('')
const typeFilter = ref('')

// Comment state
const activeCommentId = ref<string | null>(null)
const commentText = ref('')

const currentUser = 'web_user'

async function refresh() {
  await fetchApprovals({
    status: statusFilter.value || undefined,
    approval_type: typeFilter.value || undefined,
  })
}

async function handleApprove(id: string) {
  await doApprove(id, currentUser)
  await refresh()
}

async function handleReject(id: string) {
  await doReject(id, currentUser)
  await refresh()
}

async function handleRequestRevision(id: string) {
  await doRequestRevision(id, currentUser)
  await refresh()
}

function startComment(approvalId: string) {
  activeCommentId.value = approvalId
  commentText.value = ''
}

function cancelComment() {
  activeCommentId.value = null
  commentText.value = ''
}

async function submitComment(approvalId: string) {
  if (!commentText.value.trim()) return
  await doAddComment(approvalId, currentUser, commentText.value)
  cancelComment()
  await refresh()
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

onMounted(() => refresh())
</script>

<style scoped>
.approval-gate-panel {
  padding: var(--spacing-4);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.panel-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.pending-badge {
  background: var(--color-warning);
  color: white;
  border-radius: var(--radius-full);
  padding: var(--spacing-0-5) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  min-width: 24px;
  text-align: center;
}

.filter-bar {
  display: flex;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.filter-select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-6);
  justify-content: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.error-state {
  color: var(--color-error);
}

.approval-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.approval-card {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  background: var(--bg-primary);
}

.approval-card.status-pending {
  border-left: 3px solid var(--color-warning);
}

.approval-card.status-approved {
  border-left: 3px solid var(--color-success);
}

.approval-card.status-rejected {
  border-left: 3px solid var(--color-error);
}

.approval-card.status-revision_requested {
  border-left: 3px solid var(--color-info);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.approval-title {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
}

.status-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: capitalize;
}

.badge-pending {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge-approved {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge-rejected {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.badge-revision_requested {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.card-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-3);
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.card-actions {
  display: flex;
  gap: var(--spacing-2);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.add-comment-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  margin-top: var(--spacing-2);
  padding: var(--spacing-1) 0;
  border: none;
  background: none;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  cursor: pointer;
}

.add-comment-btn:hover {
  color: var(--text-secondary);
}

.comment-input {
  margin-top: var(--spacing-3);
}

.comment-textarea {
  width: 100%;
  padding: var(--spacing-2);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  resize: vertical;
  min-height: 60px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.comment-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px var(--color-info-bg);
}

.comment-input-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
}

.comments-list {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.comment-item {
  margin-bottom: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.comment-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-1);
}

.comment-author {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.comment-date {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.comment-body {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

@media (max-width: 640px) {
  .filter-bar {
    flex-direction: column;
  }

  .card-actions {
    flex-wrap: wrap;
  }

  .card-meta {
    flex-direction: column;
  }
}
</style>
