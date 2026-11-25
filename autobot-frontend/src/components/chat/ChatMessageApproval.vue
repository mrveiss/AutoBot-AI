<template>
  <!-- Decided: auto-approved (info), approved (success) or denied (error) -->
  <div v-if="confirmed" class="approval-card approval-confirmed" :class="`approval-${statusClass}`">
    <div class="approval-header">
      <Icon :name="confirmed.icon" />
      <span>{{ $t(confirmed.title) }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
        <code class="detail-value">{{ meta.command }}</code>
      </div>
      <div v-if="meta.approval_comment" class="approval-detail-item">
        <span class="detail-label">{{ $t(confirmed.commentLabel) }}:</span>
        <span class="detail-value">{{ meta.approval_comment }}</span>
      </div>
    </div>
  </div>

  <!-- Pending: only while `requires_approval` and no decision yet -->
  <div v-else-if="meta.requires_approval && !meta.approval_status" class="approval-card approval-request">
    <div class="approval-header">
      <Icon name="exclamation-triangle" />
      <span>{{ $t('chat.approval.approvalRequired') }}</span>
    </div>
    <div class="approval-details">
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
        <code class="detail-value">{{ meta.command }}</code>
      </div>
      <div class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.riskLevel') }}:</span>
        <BaseBadge class="detail-value" :variant="riskBadgeVariant(meta.risk_level)" size="sm">
          {{ meta.risk_level }}
        </BaseBadge>
      </div>
      <div v-if="meta.purpose" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.purpose') }}:</span>
        <span class="detail-value">{{ meta.purpose }}</span>
      </div>
      <div v-if="meta.reasons && meta.reasons.length > 0" class="approval-detail-item">
        <span class="detail-label">{{ $t('chat.approval.reasons') }}:</span>
        <span class="detail-value">{{ meta.reasons.join(', ') }}</span>
      </div>

      <!-- Interactive Command Warning (Issue #33) -->
      <BaseAlert v-if="meta.is_interactive" class="interactive-warning" variant="info" :title="$t('chat.approval.interactiveCommand')">
        <p>{{ $t('chat.approval.interactiveInfo') }}</p>
        <div v-if="meta.interactive_reasons && meta.interactive_reasons.length > 0" class="interactive-reasons">
          <span>{{ $t('chat.approval.inputRequired') }}:</span>
          <ul>
            <li v-for="(reason, idx) in meta.interactive_reasons" :key="idx">{{ reason }}</li>
          </ul>
        </div>
      </BaseAlert>
    </div>

    <!-- Comment input (when adding a comment) -->
    <div v-if="showCommentInput && activeCommentSessionId === meta.terminal_session_id" class="comment-input-section">
      <textarea
        v-model="approvalComment"
        class="comment-textarea"
        :placeholder="$t('chat.approval.commentPlaceholder')"
        rows="2"
        @keydown.ctrl.enter="submitComment"
        @keydown.meta.enter="submitComment"
      ></textarea>
      <div class="comment-actions">
        <BaseButton variant="secondary" size="sm" :aria-label="$t('chat.approval.cancelComment')" @click="cancelComment">
          <Icon name="times" />
          <span>{{ $t('common.cancel') }}</span>
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          :disabled="!approvalComment.trim()"
          :aria-label="$t('chat.approval.submitWithComment', { action: decisionWord })"
          @click="submitComment"
        >
          <Icon name="check" />
          <span>{{ $t('chat.approval.submit') }} {{ decisionWord }}</span>
        </BaseButton>
      </div>
    </div>

    <!-- Auto-approve similar commands -->
    <div class="approval-option">
      <label class="approval-checkbox">
        <input v-model="autoApproveFuture" type="checkbox" />
        <Icon name="shield-check" />
        <span>{{ $t('chat.approval.autoApproveFuture') }}</span>
      </label>
      <p v-if="autoApproveFuture" class="approval-hint">
        <Icon name="info-circle" />
        <span>{{ $t('chat.approval.autoApproveHint') }}</span>
      </p>
    </div>

    <!-- Permission v2: remember for this project -->
    <div v-if="permissionStore.isEnabled" class="approval-option">
      <label class="approval-checkbox">
        <input v-model="rememberForProject" type="checkbox" />
        <Icon name="folder-open" />
        <span>{{ $t('chat.approval.rememberProject') }}</span>
      </label>
      <p v-if="rememberForProject" class="approval-hint">
        <Icon name="info-circle" />
        <span>{{ $t('chat.approval.rememberProjectHint', { path: currentProjectPath || $t('chat.approval.noProjectContext') }) }}</span>
      </p>
    </div>

    <div class="approval-actions">
      <BaseButton variant="error" size="sm" :disabled="locked" :aria-label="$t('chat.approval.denyCommand')" @click="decide(false)">
        <Icon name="times" />
        <span>{{ $t('chat.approval.deny') }}</span>
      </BaseButton>
      <BaseButton
        v-if="!isGraphApproval(message.metadata)"
        variant="outline"
        size="sm"
        :disabled="locked"
        :aria-label="$t('chat.approval.addComment')"
        @click="promptForComment(sessionId)"
      >
        <Icon name="comment" />
        <span>{{ $t('chat.approval.comment') }}</span>
      </BaseButton>
      <BaseButton variant="success" size="sm" :disabled="locked" :aria-label="$t('chat.approval.approveCommand')" @click="decide(true)">
        <Icon name="check" />
        <span>{{ $t('chat.approval.approve') }}</span>
      </BaseButton>
    </div>
    <div v-if="processingApproval" class="approval-processing">
      <LoadingSpinner size="sm" />
      <span>{{ $t('chat.approval.processing') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * The inline command-approval block of a chat message (#18243, step 5a batch 2): the three
 * decided states and the pending card (comment, auto-approve, remember-for-project, actions).
 * Split out of ChatMessages.vue. The state is the ONE instance the stream provides
 * (useMessageApprovalContext), so the comment box and the processing lock stay shared as before.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import { isGraphApproval } from '@/composables/useGraphApproval'
import { useMessageApproval } from '@/composables/chat/useMessageApprovalContext'
import { riskBadgeVariant } from '@/utils/riskLevel'
import type { ChatMessage } from '@/stores/useChatStore'

const props = defineProps<{ message: ChatMessage }>()
const { t } = useI18n()

const {
  processingApproval, showCommentInput, activeCommentSessionId, approvalComment,
  pendingApprovalDecision, autoApproveFuture, rememberForProject, currentProjectPath,
  approveCommand, promptForComment, submitApprovalWithComment, cancelComment, permissionStore,
} = useMessageApproval()

/** The loosely-typed approval fields the backend puts on `metadata`. */
interface ApprovalMeta {
  approval_status?: string
  approval_comment?: string
  requires_approval?: boolean
  command?: string
  command_id?: string
  terminal_session_id?: string
  risk_level?: string
  purpose?: string
  reasons?: string[]
  is_interactive?: boolean
  interactive_reasons?: string[]
}

const CONFIRMED: Record<string, { icon: IconName; title: string; commentLabel: string }> = {
  pre_approved: { icon: 'shield-check', title: 'chat.approval.autoApproved', commentLabel: 'chat.approval.reason' },
  approved: { icon: 'check-circle', title: 'chat.approval.commandApproved', commentLabel: 'chat.approval.comment' },
  denied: { icon: 'times-circle', title: 'chat.approval.commandDenied', commentLabel: 'chat.approval.reason' },
}

const meta = computed(() => (props.message.metadata ?? {}) as ApprovalMeta)
const confirmed = computed(() => CONFIRMED[meta.value.approval_status ?? ''])
const statusClass = computed(() => (meta.value.approval_status ?? '').replace('_', '-'))
const sessionId = computed(() => meta.value.terminal_session_id as string)
const locked = computed(() => processingApproval.value || showCommentInput.value)
const decisionWord = computed(() => (pendingApprovalDecision.value ? t('chat.approval.approval') : t('chat.approval.denial')))

function decide(approved: boolean) {
  approveCommand(sessionId.value, approved, undefined, meta.value.command_id, {
    command: meta.value.command as string,
    risk_level: meta.value.risk_level as string,
  })
}

function submitComment() {
  submitApprovalWithComment(sessionId.value, pendingApprovalDecision.value)
}
</script>

<style scoped>
.approval-card {
  --approval-accent: var(--aui-color-warning);
  margin-block-start: var(--aui-space-3);
  padding: var(--aui-space-4);
  border: 1px solid color-mix(in srgb, var(--approval-accent) 45%, transparent);
  border-radius: var(--aui-radius-lg);
  background: color-mix(in srgb, var(--approval-accent) 8%, var(--aui-color-surface-raised));
  color: var(--aui-color-text);
}
.approval-pre-approved { --approval-accent: var(--aui-color-info); }
.approval-approved { --approval-accent: var(--aui-color-success); }
.approval-denied { --approval-accent: var(--aui-color-error); }

.approval-header {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  margin-block-end: var(--aui-space-3);
  color: var(--approval-accent);
  font-weight: var(--aui-font-weight-semibold);
}
.approval-details { display: flex; flex-direction: column; gap: var(--aui-space-2); margin-block-end: var(--aui-space-3); }
.approval-detail-item { display: flex; align-items: flex-start; gap: var(--aui-space-2); font-size: var(--aui-text-sm); }
.detail-label { min-inline-size: 6rem; color: var(--aui-color-text-muted); font-weight: var(--aui-font-weight-medium); }
.detail-value { flex: 1; min-inline-size: 0; }
.detail-value:is(code) {
  padding: var(--aui-space-1) var(--aui-space-2);
  overflow-x: auto;
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface-sunken);
  font-family: var(--aui-font-mono);
  font-size: var(--aui-text-xs);
}
.approval-detail-item :deep(.aui-badge) { flex: none; }

.interactive-warning { margin-block-start: var(--aui-space-2); font-size: var(--aui-text-xs); }
.interactive-reasons { margin-block-start: var(--aui-space-2); }
.interactive-reasons ul { margin: var(--aui-space-1) 0 0 var(--aui-space-4); list-style: disc; }

.comment-input-section {
  margin-block: var(--aui-space-3);
  padding: var(--aui-space-3);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface);
}
.comment-textarea {
  inline-size: 100%;
  padding: var(--aui-space-2) var(--aui-space-3);
  resize: none;
  border: 1px solid var(--aui-input-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-input-bg);
  color: var(--aui-color-text);
  font: inherit;
}
.comment-textarea:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 1px;
}
.comment-actions { display: flex; gap: var(--aui-space-2); margin-block-start: var(--aui-space-2); }

.approval-option { margin-block: var(--aui-space-3); }
.approval-checkbox {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  min-block-size: var(--aui-space-6);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  cursor: pointer;
  user-select: none;
}
.approval-checkbox input { inline-size: var(--aui-space-4); block-size: var(--aui-space-4); accent-color: var(--aui-color-primary); }
.approval-hint {
  display: flex;
  align-items: flex-start;
  gap: var(--aui-space-2);
  margin-block-start: var(--aui-space-2);
  padding-inline-start: var(--aui-space-6);
  color: var(--aui-color-info);
  font-size: var(--aui-text-xs);
}

/* Mockup: Deny, comment, Approve - right aligned. */
.approval-actions { display: flex; flex-wrap: wrap; gap: var(--aui-space-2); justify-content: flex-end; }
.approval-processing {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  margin-block-start: var(--aui-space-2);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}
@media (max-width: 768px) { .approval-actions { flex-direction: column; } }
</style>
