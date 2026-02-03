<template>
  <div v-if="showDialog" class="elevation-overlay">
    <div class="elevation-dialog">
      <div class="elevation-header">
        <div class="elevation-icon">
          <i class="fas fa-shield-alt"></i>
        </div>
        <div class="elevation-title">
          <h3>Administrator Access Required</h3>
          <p class="elevation-subtitle">{{ operation || 'This operation requires administrator privileges' }}</p>
        </div>
      </div>

      <div class="elevation-body">
        <div class="elevation-details">
          <h4>Operation Details:</h4>
          <div class="operation-info">
            <div class="info-item">
              <span class="label">Command:</span>
              <code class="command">{{ command || 'System operation' }}</code>
            </div>
            <div class="info-item" v-if="reason">
              <span class="label">Reason:</span>
              <span class="reason">{{ reason }}</span>
            </div>
            <div class="info-item" v-if="riskLevel">
              <span class="label">Risk Level:</span>
              <StatusBadge :variant="getRiskVariant(riskLevel)" size="small">{{ riskLevel }}</StatusBadge>
            </div>
          </div>
        </div>

        <div class="elevation-form">
          <div class="form-group">
            <label for="sudo-password">Administrator Password:</label>
            <div class="password-input-group">
              <input
                id="sudo-password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="password-input"
                placeholder="Enter your password"
                @keyup.enter="handleApprove"
                :disabled="isProcessing"
                autocomplete="current-password"
              />
              <button
                type="button"
                class="password-toggle"
                @click="togglePasswordVisibility"
                :disabled="isProcessing"
               aria-label="Action button">
                <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
              </button>
            </div>
          </div>

          <div class="security-options">
            <label class="checkbox-label">
              <input 
                type="checkbox" 
                v-model="rememberForSession"
                :disabled="isProcessing"
              />
              <span class="checkmark"></span>
              Remember for this session (15 minutes)
            </label>
          </div>

          <div class="warning-message" v-if="error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ error }}</span>
          </div>
        </div>
      </div>

      <div class="elevation-footer">
        <div class="button-group">
          <BaseButton
            variant="secondary"
            @click="handleCancel"
            :disabled="isProcessing"
            aria-label="Cancel">
            <i class="fas fa-times"></i>
            Cancel
          </BaseButton>
          <BaseButton
            variant="danger"
            @click="handleApprove"
            :disabled="!password"
            :loading="isProcessing"
            aria-label="Confirm">
            <i class="fas fa-check"></i>
            {{ isProcessing ? 'Verifying...' : 'Authorize' }}
          </BaseButton>
        </div>
        
        <div class="security-note">
          <i class="fas fa-info-circle"></i>
          <span>Your password is used only for this authorization and is not stored.</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { apiService } from '../services/api';
import StatusBadge from '@/components/ui/StatusBadge.vue';
import BaseButton from '@/components/base/BaseButton.vue';
import { useModal } from '@/composables/useModal';
import { useAsyncOperation } from '@/composables/useAsyncOperation';

const logger = createLogger('ElevationDialog');

export default {
  name: 'ElevationDialog',
  components: {
    StatusBadge,
    BaseButton
  },
  props: {
    show: {
      type: Boolean,
      default: false
    },
    operation: {
      type: String,
      default: ''
    },
    command: {
      type: String,
      default: ''
    },
    reason: {
      type: String,
      default: ''
    },
    riskLevel: {
      type: String,
      default: 'MEDIUM',
      validator: value => ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(value)
    },
    requestId: {
      type: String,
      required: true
    }
  },
  emits: ['approved', 'cancelled', 'close'],
  setup(props, { emit }) {
    const { isOpen: showDialog } = useModal('elevation-dialog');
    const { execute: authorize, loading: isProcessing, error } = useAsyncOperation();
    const password = ref('');
    const showPassword = ref(false);
    const rememberForSession = ref(false);

    const togglePasswordVisibility = () => {
      showPassword.value = !showPassword.value;
    };

    const authorizeFn = async () => {
      if (!password.value.trim()) {
        throw new Error('Password is required');
      }

      // Send elevation request to backend
      // Issue #552: Fixed path to match backend /api/elevation/*
      const response = await apiService.post('/api/elevation/authorize', {
        request_id: props.requestId,
        password: password.value,
        remember_session: rememberForSession.value
      });

      if (response.data.success) {
        emit('approved', {
          requestId: props.requestId,
          sessionToken: response.data.session_token
        });
        closeDialog();
      } else {
        throw new Error(response.data.message || 'Authorization failed');
      }
    };

    const handleApprove = async () => {
      await authorize(authorizeFn).catch(err => {
        // Error already handled by useAsyncOperation
        logger.error('Authorization error:', err);
      });
    };

    const handleCancel = () => {
      emit('cancelled', props.requestId);
      closeDialog();
    };

    const closeDialog = () => {
      showDialog.value = false;
      password.value = '';
      emit('close');
    };

    const handleEscape = (event) => {
      if (event.key === 'Escape' && showDialog.value && !isProcessing.value) {
        handleCancel();
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
        password.value = '';
      }
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
      password,
      showPassword,
      rememberForSession,
      isProcessing,
      error,
      togglePasswordVisibility,
      handleApprove,
      handleCancel,
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
.elevation-overlay {
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

.elevation-dialog {
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

.elevation-header {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--color-error-dark) 100%);
  color: var(--text-on-primary);
  padding: var(--spacing-5);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.elevation-icon {
  font-size: var(--font-size-3xl);
  opacity: 0.9;
}

.elevation-title h3 {
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.elevation-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  opacity: 0.9;
}

.elevation-body {
  padding: var(--spacing-6);
}

.elevation-details {
  margin-bottom: var(--spacing-6);
}

.elevation-details h4 {
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
  border-left: 4px solid var(--color-error);
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

.reason {
  color: var(--text-primary);
}

.elevation-form {
  border-top: 1px solid var(--border-primary);
  padding-top: var(--spacing-5);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.password-input-group {
  display: flex;
  align-items: center;
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color var(--duration-200);
}

.password-input-group:focus-within {
  border-color: var(--color-error);
  box-shadow: var(--shadow-focus-error);
}

.password-input {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border: none;
  outline: none;
  font-size: var(--font-size-sm);
}

.password-input:disabled {
  background: var(--bg-secondary);
  color: var(--text-disabled);
}

.password-toggle {
  padding: var(--spacing-3) var(--spacing-4);
  border: none;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  cursor: pointer;
  border-left: 1px solid var(--border-primary);
  transition: all var(--duration-200);
}

.password-toggle:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.password-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
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
  background: var(--color-error);
  border-color: var(--color-error);
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

.elevation-footer {
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

@media (max-width: 640px) {
  .elevation-dialog {
    width: 95vw;
    margin: var(--spacing-4);
  }

  .elevation-header {
    padding: var(--spacing-4);
  }

  .elevation-body {
    padding: var(--spacing-5);
  }

  .button-group {
    flex-direction: column;
  }

  .btn {
    width: 100%;
  }
}
</style>