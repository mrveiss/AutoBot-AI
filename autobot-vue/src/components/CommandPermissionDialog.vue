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
import { apiService } from '../services/api';
import appConfig from '@/config/AppConfig.js';
import StatusBadge from '@/components/ui/StatusBadge.vue';
import BaseButton from '@/components/base/BaseButton.vue';
import { useModal } from '@/composables/useModal';
import { useAsyncOperation } from '@/composables/useAsyncOperation';

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
      console.log('[CommandPermissionDialog] Status check result:', {
        isApproved: data.status === 'approved',
        isSuccess: data.status === 'success',
        isError: data.status === 'error',
        error: data.error,
        willClose: data.status === 'approved' || data.status === 'success'
      });

      // CRITICAL FIX: Handle "No pending approval" error (stale dialog from cleared session)
      if (data.status === 'error' && data.error === 'No pending approval') {
        console.warn('[CommandPermissionDialog] ⚠️ No pending approval found - this approval request is stale');
        console.warn('[CommandPermissionDialog] Closing dialog - session may have been cleared or approval already processed');

        // Close the dialog without emitting approval event
        // The session no longer has a pending approval to process
        closeDialog();

        // Show user-friendly message (optional - could use a toast notification)
        console.info('[CommandPermissionDialog] Dialog closed: This approval request is no longer valid');
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
        console.error('[CommandPermissionDialog] ❌ Status did NOT match - showing error');
        throw new Error(data.error || 'Command execution failed');
      }
    };

    const handleAllow = async () => {
      // CRITICAL: Prevent double-click/concurrent execution
      if (isProcessing.value) {
        console.warn('handleAllow: Already processing, ignoring duplicate click');
        return;
      }

      await executeAllow(allowCommandFn).catch(err => {
        // Error already handled by useAsyncOperation
        console.error('Command approval error:', err);
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
            console.warn('[CommandPermissionDialog] ⚠️ No pending approval found when denying - this approval request is stale');
            console.warn('[CommandPermissionDialog] Closing dialog - session may have been cleared or approval already processed');

            // Close the dialog without emitting denial event
            // The session no longer has a pending approval to process
            closeDialog();
            return;
          }
        } else {
          console.warn('handleDeny: terminal_session_id is missing - continuing with client-side denial');
        }

        emit('denied', {
          command: props.command,
          reason: 'User denied permission'
        });
        closeDialog();
      } catch (err) {
        console.error('Command denial error:', err);
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
      const response = await apiService.post('/chat/direct', {
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
        console.error('Comment submission error:', err);
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
.command-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.command-dialog {
  background: white;
  border-radius: 12px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  width: 90vw;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  animation: slideIn 0.3s ease-out;
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
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  color: white;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.command-icon {
  font-size: 32px;
  opacity: 0.9;
}

.command-title h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 600;
}

.command-subtitle {
  margin: 0;
  font-size: 14px;
  opacity: 0.9;
}

.command-body {
  padding: 24px;
}

.command-details {
  margin-bottom: 24px;
}

.command-details h4 {
  margin: 0 0 12px 0;
  color: #374151;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.operation-info {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #059669;
}

.info-item {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.info-item:last-child {
  margin-bottom: 0;
}

.label {
  font-weight: 600;
  color: #6b7280;
  min-width: 80px;
  font-size: 12px;
  text-transform: uppercase;
}

.command {
  background: #1f2937;
  color: #f9fafb;
  padding: 4px 8px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
}

.purpose {
  color: #374151;
}

.command-form {
  border-top: 1px solid #e5e7eb;
  padding-top: 20px;
}

.security-options {
  margin-bottom: 16px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #6b7280;
  font-size: 14px;
}

.checkbox-label input[type="checkbox"] {
  display: none;
}

.checkmark {
  width: 20px;
  height: 20px;
  border: 2px solid #d1d5db;
  border-radius: 4px;
  margin-right: 8px;
  position: relative;
  transition: all 0.2s;
}

.checkbox-label input[type="checkbox"]:checked + .checkmark {
  background: #059669;
  border-color: #059669;
}

.checkbox-label input[type="checkbox"]:checked + .checkmark::after {
  content: '✓';
  position: absolute;
  top: -2px;
  left: 3px;
  color: white;
  font-size: 14px;
  font-weight: bold;
}

.warning-message {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #991b1b;
  font-size: 14px;
}

.warning-message i {
  font-size: 16px;
}

.command-footer {
  background: #f9fafb;
  padding: 20px 24px;
  border-top: 1px solid #e5e7eb;
}

.button-group {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.security-note {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 12px;
}

.security-note i {
  font-size: 14px;
}

/* Comment Section Styles */
.comment-section {
  border-top: 1px solid #e5e7eb;
  padding-top: 20px;
  margin-top: 20px;
}

.comment-header h4 {
  margin: 0 0 8px 0;
  color: #374151;
  font-size: 14px;
  font-weight: 600;
}

.comment-header p {
  margin: 0 0 16px 0;
  color: #6b7280;
  font-size: 13px;
}

.comment-input-group {
  margin-bottom: 16px;
}

.comment-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  min-height: 80px;
  transition: border-color 0.2s;
}

.comment-textarea:focus {
  outline: none;
  border-color: #059669;
  box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.1);
}

.comment-textarea:disabled {
  background: #f9fafb;
  color: #9ca3af;
  cursor: not-allowed;
}

.comment-textarea::placeholder {
  color: #9ca3af;
  font-style: italic;
}

.comment-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .command-dialog {
    width: 95vw;
    margin: 16px;
  }

  .command-header {
    padding: 16px;
  }

  .command-body {
    padding: 20px;
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
