<template>
  <div v-if="showDialog" class="command-overlay">
    <div class="command-dialog">
      <div class="command-header">
        <div class="command-icon">
          <i class="fas fa-terminal"></i>
        </div>
        <div class="command-title">
          <h3>Command Permission Required</h3>
          <p class="command-subtitle">{{ purpose || 'The AI assistant needs to run a command' }}</p>
        </div>
      </div>

      <div class="command-body">
        <div class="command-details">
          <h4>Command Details:</h4>
          <div class="operation-info">
            <div class="info-item">
              <span class="label">Command:</span>
              <code class="command">{{ command || 'system operation' }}</code>
            </div>
            <div class="info-item" v-if="purpose">
              <span class="label">Purpose:</span>
              <span class="purpose">{{ purpose }}</span>
            </div>
            <div class="info-item" v-if="riskLevel">
              <span class="label">Risk Level:</span>
              <StatusBadge :variant="getRiskVariant(riskLevel)" size="small">{{ riskLevel }}</StatusBadge>
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
              Remember my choice for similar commands this session
            </label>
            <div id="remember-help" class="sr-only">This will apply your decision to similar commands during this session</div>
          </div>

          <div class="warning-message" v-if="error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ error }}</span>
          </div>
        </div>

        <!-- Comment Input Section -->
        <div v-if="showCommentInput" class="comment-section">
          <div class="comment-header">
            <h4>Provide Command Feedback</h4>
            <p>Suggest modifications, alternative commands, or execution order changes:</p>
          </div>

          <div class="comment-input-group">
            <textarea
              v-model="commentText"
              placeholder="e.g., 'Use ip addr instead of ifconfig' or 'Run this after checking disk space first'"
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
              <i class="fas fa-times"></i>
              Cancel
            </BaseButton>
            <BaseButton
              variant="primary"
              @click="submitComment"
              :disabled="!commentText.trim()"
              :loading="isProcessing">
              <i class="fas fa-paper-plane"></i>
              {{ isProcessing ? 'Sending...' : 'Send Feedback' }}
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
            aria-label="Deny">
            <i class="fas fa-times"></i>
            Deny
          </BaseButton>
          <BaseButton
            variant="warning"
            @click="handleComment"
            :disabled="isProcessing"
            aria-label="Comment">
            <i class="fas fa-comment"></i>
            Comment
          </BaseButton>
          <BaseButton
            variant="success"
            @click="handleAllow"
            :loading="isProcessing"
            aria-label="Allow">
            <i class="fas fa-check"></i>
            {{ isProcessing ? 'Executing...' : 'Allow' }}
          </BaseButton>
        </div>

        <div class="security-note">
          <i class="fas fa-info-circle"></i>
          <span>Commands are executed in a secure environment and logged for security.</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { apiService } from '@/services/api';
import appConfig from '@/config/AppConfig.js';
import StatusBadge from '@/components/ui/StatusBadge.vue';
import BaseButton from '@/components/base/BaseButton.vue';
import { useModal } from '@/composables/useModal';
import { useAsyncOperation } from '@/composables/useAsyncOperation';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('CommandPermissionDialog');

export default {
  name: 'CommandPermissionDialog',
  components: {
    StatusBadge,
    BaseButton
  },
  props: {
    show: {
      type: Boolean,
      default: false
    },
    command: {
      type: String,
      default: ''
    },
    purpose: {
      type: String,
      default: ''
    },
    riskLevel: {
      type: String,
      default: 'LOW',
      validator: value => ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(value)
    },
    chatId: {
      type: String,
      required: false,
      default: null
    },
    originalMessage: {
      type: String,
      default: ''
    },
    terminalSessionId: {
      type: String,
      required: false,
      default: null
    }
  },
  emits: ['approved', 'denied', 'commented', 'close'],
  setup(props, { emit }) {
    const { isOpen: showDialog } = useModal('command-permission-dialog');
    const { execute: executeAllow, loading: isProcessingAllow, error: errorAllow } = useAsyncOperation();
    const { execute: executeComment, loading: isProcessingComment, error: errorComment } = useAsyncOperation();
    const rememberForSession = ref(false);
    const showCommentInput = ref(false);
    const commentText = ref('');

    // Computed to unify loading states for template
    const isProcessing = computed(() => isProcessingAllow.value || isProcessingComment.value);
    // Computed to unify error states for template
    const error = computed(() => errorAllow.value || errorComment.value);

    const allowCommandFn = async () => {
      // Verify terminal_session_id is available
      if (!props.terminalSessionId) {
        throw new Error('Missing terminal session ID - cannot approve command');
      }

      // REFACTORED: Use AppConfig for dynamic API URL resolution
      const approvalUrl = await appConfig.getApiUrl(
        `/api/agent-terminal/sessions/${props.terminalSessionId}/approve`
      );

      // Send approval using direct fetch
      const fetchResponse = await fetch(
        approvalUrl,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            approved: true,
            user_id: 'web_user'
          })
        }
      );

      const data = await fetchResponse.json();

      // DEBUG: Log exact response to understand what we're getting
      logger.debug('Status check result:', {
        isApproved: data.status === 'approved',
        isSuccess: data.status === 'success',
        isError: data.status === 'error',
        error: data.error,
        willClose: data.status === 'approved' || data.status === 'success'
      });

      // CRITICAL FIX: Handle "No pending approval" error (stale dialog from cleared session)
      if (data.status === 'error' && data.error === 'No pending approval') {
        logger.warn('No pending approval found - this approval request is stale');
        logger.warn('Closing dialog - session may have been cleared or approval already processed');

        // Close the dialog without emitting approval event
        // The session no longer has a pending approval to process
        closeDialog();

        // Show user-friendly message (optional - could use a toast notification)
        logger.info('Dialog closed: This approval request is no longer valid');
        return;
      }

      // CRITICAL FIX: Backend returns "approved" status, not "success"
      if (data.status === 'approved' || data.status === 'success') {
        emit('approved', {
          command: props.command,
          result: data,
          rememberChoice: rememberForSession.value
        });
        closeDialog();
      } else {
        logger.error('Status did NOT match - showing error');
        throw new Error(data.error || 'Command execution failed');
      }
    };

    const handleAllow = async () => {
      // CRITICAL: Prevent double-click/concurrent execution
      if (isProcessing.value) {
        logger.warn('handleAllow: Already processing, ignoring duplicate click');
        return;
      }

      await executeAllow(allowCommandFn).catch(err => {
        // Error already handled by useAsyncOperation
        logger.error('Command approval error:', err);
      });
    };

    const handleDeny = async () => {
      try {
        // Verify terminal_session_id is available
        if (props.terminalSessionId) {
          // Send denial to agent terminal API
          const response = await apiService.post(
            `/api/agent-terminal/sessions/${props.terminalSessionId}/approve`,
            {
              approved: false,
              user_id: 'web_user'
            }
          );

          // CRITICAL FIX: Handle "No pending approval" error (stale dialog from cleared session)
          if (response.data?.status === 'error' && response.data?.error === 'No pending approval') {
            logger.warn('No pending approval found when denying - this approval request is stale');
            logger.warn('Closing dialog - session may have been cleared or approval already processed');

            // Close the dialog without emitting denial event
            // The session no longer has a pending approval to process
            closeDialog();
            return;
          }
        } else {
          logger.warn('handleDeny: terminal_session_id is missing - continuing with client-side denial');
        }

        emit('denied', {
          command: props.command,
          reason: 'User denied permission'
        });
        closeDialog();
      } catch (err) {
        logger.error('Command denial error:', err);
        // Still close dialog even if API call fails
        emit('denied', {
          command: props.command,
          reason: 'User denied permission'
        });
        closeDialog();
      }
    };

    const handleComment = () => {
      showCommentInput.value = true;
    };

    const submitCommentFn = async () => {
      if (!commentText.value.trim()) {
        throw new Error('Please enter a comment');
      }

      // Send comment to backend
      // Issue #552: Fixed missing /api prefix
      const response = await apiService.post('/api/chat/direct', {
        message: `Command feedback: ${commentText.value}`,
        chat_id: props.chatId
      });

      emit('commented', {
        command: props.command,
        comment: commentText.value,
        response: response.data
      });
      closeDialog();
    };

    const submitComment = async () => {
      await executeComment(submitCommentFn).catch(err => {
        // Error already handled by useAsyncOperation
        logger.error('Comment submission error:', err);
      });
    };

    const cancelComment = () => {
      showCommentInput.value = false;
      commentText.value = '';
    };

    const closeDialog = () => {
      showDialog.value = false;
      rememberForSession.value = false;
      emit('close');
    };

    const handleEscape = (event) => {
      if (event.key === 'Escape' && showDialog.value && !isProcessing.value) {
        handleDeny();
      }
    };

    onMounted(() => {
      showDialog.value = props.show;
      document.addEventListener('keydown', handleEscape);
    });

    onUnmounted(() => {
      document.removeEventListener('keydown', handleEscape);
    });

    // Watch for show prop changes
    const updateShow = (newValue) => {
      showDialog.value = newValue;
    };

    // StatusBadge variant mapping function
    const getRiskVariant = (riskLevel) => {
      const variantMap = {
        'LOW': 'success',
        'MEDIUM': 'warning',
        'HIGH': 'danger',
        'CRITICAL': 'danger'
      };
      return variantMap[riskLevel] || 'secondary';
    };

    return {
      showDialog,
      rememberForSession,
      isProcessing,
      error,
      showCommentInput,
      commentText,
      handleAllow,
      handleDeny,
      handleComment,
      submitComment,
      cancelComment,
      updateShow,
      getRiskVariant
    };
  },
  watch: {
    show: {
      handler(newValue) {
        this.updateShow(newValue);
      },
      immediate: true
    }
  }
};
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
  z-index: 10000;
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
  background: linear-gradient(135deg, var(--color-success) 0%, var(--color-success-dark) 100%);
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
  margin: 0;
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
  margin-bottom: 0;
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
