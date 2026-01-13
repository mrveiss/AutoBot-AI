<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="session-wizard">
    <div class="wizard-card">
      <div class="wizard-header">
        <h4><i class="fas fa-plus-circle"></i> Create Desktop Streaming Session</h4>
        <p>Set up a new desktop streaming session for remote access</p>
      </div>

      <form @submit.prevent="handleSubmit" class="wizard-form">
        <div class="form-group">
          <label for="user-id">User ID</label>
          <input
            id="user-id"
            v-model="form.user_id"
            type="text"
            placeholder="Enter user identifier"
            required
          />
          <span class="help-text">Unique identifier for the session user</span>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="resolution">Resolution</label>
            <select id="resolution" v-model="form.resolution">
              <option
                v-for="res in availableResolutions"
                :key="res"
                :value="res"
              >
                {{ res }}
              </option>
            </select>
            <span class="help-text">Desktop display resolution</span>
          </div>

          <div class="form-group">
            <label for="depth">Color Depth</label>
            <select id="depth" v-model="form.depth">
              <option
                v-for="d in availableDepths"
                :key="d"
                :value="d"
              >
                {{ d }}-bit
              </option>
            </select>
            <span class="help-text">Display color depth</span>
          </div>
        </div>

        <div class="capabilities-info" v-if="capabilities">
          <h5>System Capabilities</h5>
          <div class="capability-items">
            <div class="capability-item">
              <i class="fas" :class="capabilities.vnc_available ? 'fa-check text-success' : 'fa-times text-error'"></i>
              <span>VNC Server</span>
            </div>
            <div class="capability-item">
              <i class="fas" :class="capabilities.novnc_available ? 'fa-check text-success' : 'fa-times text-error'"></i>
              <span>noVNC Web Access</span>
            </div>
            <div class="capability-item">
              <i class="fas fa-desktop"></i>
              <span>Max Sessions: {{ capabilities.max_sessions }}</span>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn-primary" :disabled="loading || !isValid">
            <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-play'"></i>
            {{ loading ? 'Creating...' : 'Create Session' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { StreamingCapabilities } from '@/utils/AdvancedControlApiClient';

const props = defineProps<{
  capabilities: StreamingCapabilities | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  create: [request: { user_id: string; resolution: string; depth: number }];
}>();

const form = ref({
  user_id: '',
  resolution: '1024x768',
  depth: 24,
});

const availableResolutions = computed(() => {
  if (props.capabilities?.supported_resolutions?.length) {
    return props.capabilities.supported_resolutions;
  }
  return ['800x600', '1024x768', '1280x720', '1280x1024', '1920x1080'];
});

const availableDepths = computed(() => {
  if (props.capabilities?.supported_depths?.length) {
    return props.capabilities.supported_depths;
  }
  return [8, 16, 24, 32];
});

const isValid = computed(() => {
  return form.value.user_id.trim().length > 0;
});

const handleSubmit = () => {
  if (!isValid.value) return;
  emit('create', {
    user_id: form.value.user_id.trim(),
    resolution: form.value.resolution,
    depth: form.value.depth,
  });
};
</script>

<style scoped>
.session-wizard {
  max-width: 600px;
}

.wizard-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.wizard-header {
  padding: 24px;
  border-bottom: 1px solid var(--border-default);
}

.wizard-header h4 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.wizard-header h4 i {
  color: var(--color-primary);
}

.wizard-header p {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

.wizard-form {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.form-group input,
.form-group select {
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
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-group input::placeholder {
  color: var(--text-muted);
}

.help-text {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.capabilities-info {
  margin: 24px 0;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.capabilities-info h5 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.capability-items {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.capability-item i {
  width: 16px;
  text-align: center;
}

.text-success {
  color: var(--color-success);
}

.text-error {
  color: var(--color-error);
}

.form-actions {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  padding: 12px 24px;
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

@media (max-width: 480px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
