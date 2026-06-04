<template>
  <div v-if="showDialog" class="command-overlay">
    <div ref="dialogRef" class="command-dialog" role="dialog" aria-modal="true" aria-labelledby="cmd-permission-title" @keydown="onKeydown">
      <div class="command-header">
        <div class="command-icon" aria-hidden="true">
          <Icon name="terminal" size="md" />
        </div>
        <div class="command-title">
          <h3 id="cmd-permission-title">{{ t('ui.commandPermission.title') }}</h3>
          <p class="command-subtitle">{{ purpose || t('ui.commandPermission.defaultPurpose') }}</p>
        </div>
      </div>

      <div class="command-body">
        <div class="command-details">
          <h4>{{ t('ui.commandPermission.commandDetails') }}:</h4>
          <div class="operation-info">
            <div class="info-item">
              <span class="label">{{ t('ui.commandPermission.commandLabel') }}:</span>
              <code class="command">{{ command || t('ui.commandPermission.systemOperation') }}</code>
            </div>
            <div class="info-item" v-if="purpose">
              <span class="label">{{ t('ui.commandPermission.purposeLabel') }}:</span>
              <span class="purpose">{{ purpose }}</span>
            </div>
            <div class="info-item" v-if="riskLevel">
              <span class="label">{{ t('ui.commandPermission.riskLevelLabel') }}:</span>
              <StatusBadge :variant="getRiskVariant(riskLevel)" size="sm">{{ riskLevel }}</StatusBadge>
            </div>
          </div>
        </div>

        <div class="command-form">
          <div class="security-options">
            <label class="checkbox-label">
              <input
                type="checkbox"
                v-model="rememberForSession"
                :disabled="isProcessing"
                id="remember-session"
                aria-describedby="remember-help"
              />
              <span class="checkmark"></span>
              {{ t('ui.commandPermission.rememberChoice') }}
            </label>
            <div id="remember-help" class="sr-only">{{ t('ui.commandPermission.rememberHelp') }}</div>
          </div>

          <div class="warning-message" v-if="error">
            <Icon name="exclamation-triangle" size="sm" />
            <span>{{ error }}</span>
          </div>
        </div>

        <!-- Comment Input Section -->
        <div v-if="showCommentInput" class="comment-section">
          <div class="comment-header">
            <h4>{{ t('ui.commandPermission.feedbackTitle') }}</h4>
            <p>{{ t('ui.commandPermission.feedbackDescription') }}</p>
          </div>

          <div class="comment-input-group">
            <textarea
              v-model="commentText"
              :placeholder="t('ui.commandPermission.feedbackPlaceholder')"
              class="comment-textarea"
              rows="3"
              :disabled="isProcessing"
            ></textarea>
          </div>

          <div class="comment-actions">
            <BaseButton
              variant="secondary"
              @click="cancelComment"
              :disabled="isProcessing">
              <Icon name="times" size="sm" />
              {{ t('ui.commandPermission.cancel') }}
            </BaseButton>
            <BaseButton
              variant="primary"
              @click="submitComment"
              :disabled="!commentText.trim()"
              :loading="isProcessing">
              <Icon name="paper-plane" size="sm" />
              {{ isProcessing ? t('ui.commandPermission.sending') : t('ui.commandPermission.sendFeedback') }}
            </BaseButton>
          </div>
        </div>
      </div>

      <div class="command-footer">
        <div class="button-group">
          <BaseButton
            variant="secondary"
            @click="handleDeny"
            :disabled="isProcessing"
            :aria-label="t('ui.commandPermission.deny')">
            <Icon name="times" size="sm" />
            {{ t('ui.commandPermission.deny') }}
          </BaseButton>
          <BaseButton
            variant="warning"
            @click="handleComment"
            :disabled="isProcessing"
            :aria-label="t('ui.commandPermission.comment')">
            <Icon name="comment" size="sm" />
            {{ t('ui.commandPermission.comment') }}
          </BaseButton>
          <BaseButton
            variant="success"
            @click="handleAllow"
            :loading="isProcessing"
            :aria-label="t('ui.commandPermission.allow')">
            <Icon name="check" size="sm" />
            {{ isProcessing ? t('ui.commandPermission.executing') : t('ui.commandPermission.allow') }}
          </BaseButton>
        </div>

        <div class="security-note">
          <Icon name="info-circle" size="sm" />
          <span>{{ t('ui.commandPermission.securityNote') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import Icon from '@/components/ui/Icon.vue'
import { useModal } from '@/composables/useModal'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { createLogger } from '@/utils/debugUtils'
import { useCommandPermissions } from '@/composables/useCommandPermissions'

const logger = createLogger('CommandPermissionDialog')
const { t } = useI18n()
const { isProcessing, error, errorApprove, errorComment, approveOrDeny, postComment } = useCommandPermissions()

const props = defineProps<{
  show?: boolean
  command?: string
  purpose?: string
  riskLevel?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  chatId?: string | null
  originalMessage?: string
  terminalSessionId?: string | null
}>()

const emit = defineEmits<{
  (e: 'approved', payload: { command: string; result: unknown; rememberChoice: boolean }): void
  (e: 'denied', payload: { command: string; reason: string }): void
  (e: 'commented', payload: { command: string; comment: string; response: unknown }): void
  (e: 'close'): void
}>()

const { isOpen: showDialog } = useModal({ id: 'command-permission-dialog' })
const rememberForSession = ref(false)
const showCommentInput = ref(false)
const commentText = ref('')

// Focus trap and restore
const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(dialogRef)
useFocusRestore(showDialog)

const handleAllow = async () => {
  if (isProcessing.value) return
  if (!props.terminalSessionId) {
    errorApprove.value = new Error(t('ui.commandPermission.missingSessionId'))
    return
  }
  try {
    const data = await approveOrDeny(props.terminalSessionId, true)
    logger.debug('Status check result:', {
      isApproved: data.status === 'approved',
      isSuccess: data.status === 'success',
      isError: data.status === 'error',
      error: data.error,
      willClose: data.status === 'approved' || data.status === 'success'
    })
    if (data.status === 'error' && data.error === 'No pending approval') {
      logger.warn('No pending approval found - this approval request is stale')
      closeDialog()
      return
    }
    if (data.status === 'approved' || data.status === 'success') {
      emit('approved', { command: props.command ?? '', result: data, rememberChoice: rememberForSession.value })
      closeDialog()
    } else {
      errorApprove.value = new Error(data.error ?? t('ui.commandPermission.executionFailed'))
      logger.error('Command approval error:', data.error)
    }
  } catch (err) {
    errorApprove.value = err instanceof Error ? err : new Error(String(err))
    logger.error('Command approval error:', err)
  }
}

const handleDeny = async () => {
  try {
    if (props.terminalSessionId) {
      const data = await approveOrDeny(props.terminalSessionId, false)
      if (data.status === 'error' && data.error === 'No pending approval') {
        logger.warn('No pending approval found when denying - stale dialog, closing')
        closeDialog()
        return
      }
    } else {
      logger.warn('handleDeny: terminal_session_id is missing')
    }
    emit('denied', { command: props.command ?? '', reason: 'User denied permission' })
    closeDialog()
  } catch (err) {
    logger.error('Command denial error:', err)
    emit('denied', { command: props.command ?? '', reason: 'User denied permission' })
    closeDialog()
  }
}

const handleComment = () => { showCommentInput.value = true }

const submitComment = async () => {
  if (!commentText.value.trim()) {
    errorComment.value = new Error(t('ui.commandPermission.enterComment'))
    return
  }
  try {
    const response = await postComment(props.chatId, `Command feedback: ${commentText.value}`)
    emit('commented', { command: props.command ?? '', comment: commentText.value, response })
    closeDialog()
  } catch (err) {
    errorComment.value = err instanceof Error ? err : new Error(String(err))
    logger.error('Comment submission error:', err)
  }
}

const cancelComment = () => {
  showCommentInput.value = false
  commentText.value = ''
}

const closeDialog = () => {
  showDialog.value = false
  rememberForSession.value = false
  emit('close')
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && showDialog.value && !isProcessing.value) handleDeny()
}

onMounted(() => {
  showDialog.value = props.show ?? false
  document.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleEscape)
})

watch(() => props.show, (newValue) => {
  showDialog.value = newValue ?? false
}, { immediate: true })

const getRiskVariant = (riskLevel: string): 'success' | 'warning' | 'info' | 'primary' | 'secondary' | 'error' | undefined => {
  const variantMap: Record<string, 'success' | 'warning' | 'error' | 'secondary'> = { LOW: 'success', MEDIUM: 'warning', HIGH: 'error', CRITICAL: 'error' }
  return variantMap[riskLevel] ?? 'secondary'
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.command-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-maximum);
  backdrop-filter: blur(4px);
}

.command-dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  width: 90vw;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  animation: slideIn var(--duration-300) var(--ease-out);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.command-header {
  background: var(--color-success);
  color: var(--text-on-primary);
  padding: var(--spacing-5);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.command-icon {
  font-size: var(--font-size-3xl);
  opacity: 0.9;
}

.command-title h3 {
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.command-subtitle {
  margin: var(--spacing-0);
  font-size: var(--font-size-sm);
  opacity: 0.9;
}

.command-body {
  padding: var(--spacing-6);
}

.command-details {
  margin-bottom: var(--spacing-6);
}

.command-details h4 {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.operation-info {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  border-left: 4px solid var(--color-success);
}

.info-item {
  display: flex;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.info-item:last-child {
  margin-bottom: var(--spacing-0);
}

.label {
  font-weight: var(--font-weight-semibold);
  color: var(--text-tertiary);
  min-width: 80px;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
}

.command {
  background: var(--bg-inverse);
  color: var(--text-inverse);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.purpose {
  color: var(--text-primary);
}

.command-form {
  border-top: 1px solid var(--border-primary);
  padding-top: var(--spacing-5);
}

.security-options {
  margin-bottom: var(--spacing-4);
}

.checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

.checkbox-label input[type="checkbox"] {
  display: none;
}

.checkmark {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-secondary);
  border-radius: var(--radius-sm);
  margin-right: var(--spacing-2);
  position: relative;
  transition: all var(--duration-200);
}

.checkbox-label input[type="checkbox"]:checked + .checkmark {
  background: var(--color-success);
  border-color: var(--color-success);
}

.checkbox-label input[type="checkbox"]:checked + .checkmark::after {
  content: '✓';
  position: absolute;
  top: -2px;
  left: 3px;
  color: var(--text-on-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.warning-message {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-error-dark);
  font-size: var(--font-size-sm);
}

.warning-message i {
  font-size: var(--font-size-base);
}

.command-footer {
  background: var(--bg-secondary);
  padding: var(--spacing-5) var(--spacing-6);
  border-top: 1px solid var(--border-primary);
}

.button-group {
  display: flex;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-3);
}

.security-note {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
}

.security-note i {
  font-size: var(--font-size-sm);
}

/* Comment Section Styles */
.comment-section {
  border-top: 1px solid var(--border-primary);
  padding-top: var(--spacing-5);
  margin-top: var(--spacing-5);
}

.comment-header h4 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.comment-header p {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
}

.comment-input-group {
  margin-bottom: var(--spacing-4);
}

.comment-textarea {
  width: 100%;
  padding: var(--spacing-3);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: inherit;
  resize: vertical;
  min-height: 80px;
  transition: border-color var(--duration-200);
}

.comment-textarea:focus {
  outline: none;
  border-color: var(--color-success);
  box-shadow: var(--shadow-focus-success);
}
.comment-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.comment-textarea:disabled {
  background: var(--bg-secondary);
  color: var(--text-disabled);
  cursor: not-allowed;
}

.comment-textarea::placeholder {
  color: var(--text-disabled);
  font-style: italic;
}

.comment-actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .command-dialog {
    width: 95vw;
    margin: var(--spacing-4);
  }

  .command-header {
    padding: var(--spacing-4);
  }

  .command-body {
    padding: var(--spacing-5);
  }

  .button-group {
    flex-direction: column;
  }

  .btn {
    width: 100%;
  }

  .comment-actions {
    flex-direction: column;
  }

  .comment-actions .btn {
    width: 100%;
  }
}
</style>
