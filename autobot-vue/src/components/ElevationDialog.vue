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
.elevation-overlay {
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

.elevation-dialog {
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

.elevation-header {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
  color: white;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.elevation-icon {
  font-size: 32px;
  opacity: 0.9;
}

.elevation-title h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 600;
}

.elevation-subtitle {
  margin: 0;
  font-size: 14px;
  opacity: 0.9;
}

.elevation-body {
  padding: 24px;
}

.elevation-details {
  margin-bottom: 24px;
}

.elevation-details h4 {
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
  border-left: 4px solid #dc2626;
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

.reason {
  color: #374151;
}

.elevation-form {
  border-top: 1px solid #e5e7eb;
  padding-top: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #374151;
}

.password-input-group {
  display: flex;
  align-items: center;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.password-input-group:focus-within {
  border-color: #dc2626;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
}

.password-input {
  flex: 1;
  padding: 12px 16px;
  border: none;
  outline: none;
  font-size: 14px;
}

.password-input:disabled {
  background: #f9fafb;
  color: #9ca3af;
}

.password-toggle {
  padding: 12px 16px;
  border: none;
  background: #f9fafb;
  color: #6b7280;
  cursor: pointer;
  border-left: 1px solid #e5e7eb;
  transition: all 0.2s;
}

.password-toggle:hover:not(:disabled) {
  background: #f3f4f6;
  color: #374151;
}

.password-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
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
  background: #dc2626;
  border-color: #dc2626;
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

.elevation-footer {
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

@media (max-width: 640px) {
  .elevation-dialog {
    width: 95vw;
    margin: 16px;
  }
  
  .elevation-header {
    padding: 16px;
  }
  
  .elevation-body {
    padding: 20px;
  }
  
  .button-group {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }
}
</style>