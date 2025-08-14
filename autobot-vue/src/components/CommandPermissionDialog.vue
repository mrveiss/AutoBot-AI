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
              <span class="risk-badge" :class="riskLevel.toLowerCase()">{{ riskLevel }}</span>
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
              />
              <span class="checkmark"></span>
              Remember my choice for similar commands this session
            </label>
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
            <button
              class="btn btn-secondary"
              @click="cancelComment"
              :disabled="isProcessing">
              <i class="fas fa-times"></i>
              Cancel
            </button>
            <button
              class="btn btn-primary"
              @click="submitComment"
              :disabled="!commentText.trim() || isProcessing">
              <i v-if="isProcessing" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-paper-plane"></i>
              {{ isProcessing ? 'Sending...' : 'Send Feedback' }}
            </button>
          </div>
        </div>
      </div>

      <div class="command-footer">
        <div class="button-group">
          <button
            class="btn btn-cancel"
            @click="handleDeny"
            :disabled="isProcessing"
            aria-label="Deny">
            <i class="fas fa-times"></i>
            Deny
          </button>
          <button
            class="btn btn-comment"
            @click="handleComment"
            :disabled="isProcessing"
            aria-label="Comment">
            <i class="fas fa-comment"></i>
            Comment
          </button>
          <button
            class="btn btn-allow"
            @click="handleAllow"
            :disabled="isProcessing"
            :class="{ processing: isProcessing }"
            aria-label="Allow">
            <i v-if="isProcessing" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-check"></i>
            {{ isProcessing ? 'Executing...' : 'Allow' }}
          </button>
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
import { ref, onMounted, onUnmounted } from 'vue';
import { apiService } from '../services/api';

export default {
  name: 'CommandPermissionDialog',
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
      required: true
    },
    originalMessage: {
      type: String,
      default: ''
    }
  },
  emits: ['approved', 'denied', 'commented', 'close'],
  setup(props, { emit }) {
    const showDialog = ref(false);
    const rememberForSession = ref(false);
    const isProcessing = ref(false);
    const error = ref('');
    const showCommentInput = ref(false);
    const commentText = ref('');

    const handleAllow = async () => {
      isProcessing.value = true;
      error.value = '';

      try {
        // Send approval to chat endpoint with "yes" response
        const response = await apiService.post('/chat/direct', {
          message: 'yes',
          chat_id: props.chatId,
          remember_choice: rememberForSession.value
        });

        if (response.data) {
          emit('approved', {
            command: props.command,
            result: response.data,
            rememberChoice: rememberForSession.value
          });
          closeDialog();
        } else {
          error.value = 'Command execution failed';
        }
      } catch (err) {
        console.error('Command approval error:', err);
        error.value = err.response?.data?.message || 'Command execution failed';
      } finally {
        isProcessing.value = false;
      }
    };

    const handleDeny = async () => {
      try {
        // Send denial to chat endpoint with "no" response
        await apiService.post('/chat/direct', {
          message: 'no',
          chat_id: props.chatId
        });

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
      error.value = '';
    };

    const submitComment = async () => {
      if (!commentText.value.trim()) {
        error.value = 'Please enter a comment';
        return;
      }

      isProcessing.value = true;
      error.value = '';

      try {
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
      } catch (err) {
        console.error('Comment submission error:', err);
        error.value = err.response?.data?.message || 'Failed to submit comment';
      } finally {
        isProcessing.value = false;
      }
    };

    const cancelComment = () => {
      showCommentInput.value = false;
      commentText.value = '';
      error.value = '';
    };

    const closeDialog = () => {
      showDialog.value = false;
      error.value = '';
      isProcessing.value = false;
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
      if (newValue) {
        error.value = '';
      }
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
      updateShow
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

.risk-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.risk-badge.low {
  background: #d1fae5;
  color: #065f46;
}

.risk-badge.medium {
  background: #fef3c7;
  color: #92400e;
}

.risk-badge.high {
  background: #fee2e2;
  color: #991b1b;
}

.risk-badge.critical {
  background: #fecaca;
  color: #7f1d1d;
  border: 1px solid #f87171;
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

.btn {
  flex: 1;
  padding: 12px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.btn-cancel {
  background: #f3f4f6;
  color: #6b7280;
}

.btn-cancel:hover:not(:disabled) {
  background: #e5e7eb;
  color: #374151;
}

.btn-allow {
  background: #059669;
  color: white;
}

.btn-allow:hover:not(:disabled) {
  background: #047857;
}

.btn-allow.processing {
  background: #6b7280;
}

.btn-comment {
  background: #f59e0b;
  color: white;
}

.btn-comment:hover:not(:disabled) {
  background: #d97706;
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

.btn-secondary {
  background: #f3f4f6;
  color: #6b7280;
}

.btn-secondary:hover:not(:disabled) {
  background: #e5e7eb;
  color: #374151;
}

.btn-primary {
  background: #059669;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #047857;
}

.btn-primary:disabled {
  background: #9ca3af;
  cursor: not-allowed;
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
