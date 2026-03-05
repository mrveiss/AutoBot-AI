<template>
  <!-- PRE-APPROVED STATE - Show blue auto-approval -->
  <div v-if="status === 'pre_approved'" class="approval-confirmed approval-pre-approved">
    <div class="approval-header">
      <i class="fas fa-shield-check text-blue-600" aria-hidden="true"></i>
      <span class="font-semibold">{{ $t('chat.approval.autoApproved') }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}</span>
        <code class="detail-value">{{ command }}</code>
      </div>
      <div v-if="comment" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.reason') }}</span>
        <span class="detail-value">{{ comment }}</span>
      </div>
    </div>
  </div>

  <!-- USER APPROVED STATE - Show green confirmation -->
  <div v-else-if="status === 'approved'" class="approval-confirmed approval-approved">
    <div class="approval-header">
      <i class="fas fa-check-circle text-green-600" aria-hidden="true"></i>
      <span class="font-semibold">{{ $t('chat.approval.commandApproved') }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}</span>
        <code class="detail-value">{{ command }}</code>
      </div>
      <div v-if="comment" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.comment') }}</span>
        <span class="detail-value">{{ comment }}</span>
      </div>
    </div>
  </div>

  <!-- DENIED STATE - Show red rejection -->
  <div v-else-if="status === 'denied'" class="approval-confirmed approval-denied">
    <div class="approval-header">
      <i class="fas fa-times-circle text-red-600" aria-hidden="true"></i>
      <span class="font-semibold">{{ $t('chat.approval.commandDenied') }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}</span>
        <code class="detail-value">{{ command }}</code>
      </div>
      <div v-if="comment" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.reason') }}</span>
        <span class="detail-value">{{ comment }}</span>
      </div>
    </div>
  </div>

  <!-- PENDING APPROVAL STATE - Show approval buttons -->
  <div v-else-if="requiresApproval && !status" class="approval-request">
    <div class="approval-header">
      <i class="fas fa-exclamation-triangle text-yellow-600" aria-hidden="true"></i>
      <span class="font-semibold">{{ $t('chat.approval.approvalRequired') }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}</span>
        <code class="detail-value">{{ command }}</code>
      </div>
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.riskLevel') }}</span>
        <span class="detail-value" :class="getRiskClass(riskLevel)">
          {{ riskLevel }}
        </span>
      </div>
      <div v-if="purpose" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.purpose') }}</span>
        <span class="detail-value">{{ purpose }}</span>
      </div>
      <div v-if="reasons && reasons.length > 0" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.reasons') }}</span>
        <span class="detail-value">{{ reasons.join(', ') }}</span>
      </div>

      <!-- Interactive Command Warning (Issue #33) -->
      <div v-if="isInteractive" class="approval-detail-item interactive-warning">
        <div class="interactive-header">
          <i class="fas fa-keyboard text-blue-600" aria-hidden="true"></i>
          <span class="detail-label font-semibold text-blue-700">{{ $t('chat.approval.interactiveCommand') }}</span>
        </div>
        <div class="interactive-info">
          <p class="text-sm text-autobot-text-secondary mb-2">
            {{ $t('chat.approval.interactiveInfo') }}
          </p>
          <div
            v-if="interactiveReasons && interactiveReasons.length > 0"
            class="interactive-reasons"
          >
            <span class="text-xs font-medium text-autobot-text-secondary">{{ $t('chat.approval.inputRequiredFor') }}</span>
            <ul class="text-xs text-autobot-text-secondary mt-1 ml-4 list-disc">
              <li v-for="(reason, idx) in interactiveReasons" :key="idx">{{ reason }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Comment input (when adding comment) -->
    <div v-if="showCommentInput" class="comment-input-section">
      <textarea
        v-model="localComment"
        class="comment-textarea"
        :placeholder="$t('chat.approval.commentPlaceholder')"
        rows="2"
        @keydown.ctrl.enter="submitWithComment"
        @keydown.meta.enter="submitWithComment"
      ></textarea>
      <div class="comment-actions">
        <BaseButton
          variant="secondary"
          size="sm"
          @click="cancelComment"
          class="cancel-comment-btn"
          :aria-label="$t('chat.approval.cancelComment')"
        >
          <i class="fas fa-times" aria-hidden="true"></i>
          <span>{{ $t('common.cancel') }}</span>
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          @click="submitWithComment"
          :disabled="!localComment.trim()"
          class="submit-comment-btn"
          :aria-label="$t('chat.approval.submitDecision', { decision: pendingDecision ? $t('chat.approval.approval') : $t('chat.approval.denial') })"
        >
          <i class="fas fa-check" aria-hidden="true"></i>
          <span>{{ $t('chat.approval.submitDecision', { decision: pendingDecision ? $t('chat.approval.approval') : $t('chat.approval.denial') }) }}</span>
        </BaseButton>
      </div>
    </div>

    <!-- Auto-approve checkbox for future similar commands -->
    <div class="auto-approve-section">
      <label class="auto-approve-checkbox">
        <input
          type="checkbox"
          v-model="localAutoApprove"
          class="checkbox-input"
          @change="$emit('auto-approve-changed', localAutoApprove)"
        />
        <span class="checkbox-label">
          <i class="fas fa-shield-check" aria-hidden="true"></i>
          {{ $t('chat.approval.autoApproveLabel') }}
        </span>
      </label>
      <div v-if="localAutoApprove" class="auto-approve-hint">
        <i class="fas fa-info-circle" aria-hidden="true"></i>
        <span>{{ $t('chat.approval.autoApproveHint') }}</span>
      </div>
    </div>

    <!-- Approval buttons -->
    <div class="approval-actions">
      <BaseButton
        variant="danger"
        size="sm"
        @click="startDeny"
        :disabled="processing"
        class="deny-btn"
        :aria-label="$t('chat.approval.denyCommand')"
      >
        <i class="fas fa-times" aria-hidden="true"></i>
        <span>{{ $t('chat.approval.deny') }}</span>
      </BaseButton>
      <BaseButton
        variant="secondary"
        size="sm"
        @click="startDenyWithComment"
        :disabled="processing"
        class="deny-comment-btn"
        :aria-label="$t('chat.approval.denyWithComment')"
      >
        <i class="fas fa-comment" aria-hidden="true"></i>
        <span>{{ $t('chat.approval.denyWithComment') }}</span>
      </BaseButton>
      <BaseButton
        variant="secondary"
        size="sm"
        @click="startApproveWithComment"
        :disabled="processing"
        class="approve-comment-btn"
        :aria-label="$t('chat.approval.approveWithComment')"
      >
        <i class="fas fa-comment" aria-hidden="true"></i>
        <span>{{ $t('chat.approval.approveWithComment') }}</span>
      </BaseButton>
      <BaseButton
        variant="success"
        size="sm"
        @click="startApprove"
        :disabled="processing"
        class="approve-btn"
        :aria-label="$t('chat.approval.approveCommand')"
      >
        <i class="fas fa-check" aria-hidden="true"></i>
        <span>{{ $t('chat.approval.approve') }}</span>
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Approval Request Card Component
 *
 * Displays command approval states and handles user approval decisions.
 * Extracted from ChatMessages.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'

const { t } = useI18n()

interface Props {
  status?: string | null // 'pre_approved' | 'approved' | 'denied' | null
  requiresApproval?: boolean
  command?: string
  comment?: string
  riskLevel?: string
  purpose?: string
  reasons?: string[]
  isInteractive?: boolean
  interactiveReasons?: string[]
  processing?: boolean
  sessionId?: string | null
}

interface Emits {
  (e: 'approve', sessionId: string | null, comment?: string, autoApprove?: boolean): void
  (e: 'deny', sessionId: string | null, comment?: string): void
  (e: 'auto-approve-changed', value: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  status: null,
  requiresApproval: false,
  command: '',
  comment: '',
  riskLevel: 'low',
  purpose: '',
  reasons: () => [],
  isInteractive: false,
  interactiveReasons: () => [],
  processing: false,
  sessionId: null
})

const emit = defineEmits<Emits>()

// Local state
const showCommentInput = ref(false)
const localComment = ref('')
const pendingDecision = ref<boolean | null>(null)
const localAutoApprove = ref(false)

// Reset state when status changes
watch(
  () => props.status,
  () => {
    showCommentInput.value = false
    localComment.value = ''
    pendingDecision.value = null
  }
)

// Helpers
const getRiskClass = (level: string): string => {
  const classes: Record<string, string> = {
    low: 'risk-low',
    medium: 'risk-medium',
    high: 'risk-high',
    critical: 'risk-critical'
  }
  return classes[level?.toLowerCase()] || 'risk-low'
}

// Actions
const startApprove = () => {
  emit('approve', props.sessionId, undefined, localAutoApprove.value)
}

const startDeny = () => {
  emit('deny', props.sessionId, undefined)
}

const startApproveWithComment = () => {
  pendingDecision.value = true
  showCommentInput.value = true
}

const startDenyWithComment = () => {
  pendingDecision.value = false
  showCommentInput.value = true
}

const cancelComment = () => {
  showCommentInput.value = false
  localComment.value = ''
  pendingDecision.value = null
}

const submitWithComment = () => {
  if (!localComment.value.trim()) return

  if (pendingDecision.value) {
    emit('approve', props.sessionId, localComment.value, localAutoApprove.value)
  } else {
    emit('deny', props.sessionId, localComment.value)
  }

  cancelComment()
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.approval-confirmed,
.approval-request {
  margin-top: var(--spacing-3);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3) var(--spacing-4);
}

.approval-pre-approved {
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-bg-hover);
}

.approval-approved {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
}

.approval-denied {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
}

.approval-request {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
}

.approval-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
  font-size: var(--text-sm);
}

.approval-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.approval-detail-item {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.detail-label {
  color: var(--text-tertiary);
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  color: var(--text-primary);
  word-break: break-word;
}

.detail-value code {
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.risk-low {
  color: var(--color-success);
}

.risk-medium {
  color: var(--color-warning);
}

.risk-high {
  color: var(--color-error);
}

.risk-critical {
  color: var(--color-error-hover);
  font-weight: var(--font-semibold);
}

.interactive-warning {
  flex-direction: column;
  margin-top: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-info-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-info-bg-hover);
}

.interactive-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  margin-bottom: var(--spacing-2);
}

.interactive-info {
  margin-left: var(--spacing-6);
}

.comment-input-section {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.comment-textarea {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  resize: vertical;
  min-height: 60px;
}

.comment-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px var(--color-info-bg);
}

.comment-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
}

.auto-approve-section {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.auto-approve-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.checkbox-input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-info);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.auto-approve-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  margin-top: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-info-bg);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.approval-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.approve-btn,
.deny-btn,
.approve-comment-btn,
.deny-comment-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

@media (max-width: 640px) {
  .approval-actions {
    flex-wrap: wrap;
  }

  .approval-detail-item {
    flex-direction: column;
    gap: var(--spacing-0-5);
  }

  .detail-label {
    min-width: unset;
  }
}
</style>
