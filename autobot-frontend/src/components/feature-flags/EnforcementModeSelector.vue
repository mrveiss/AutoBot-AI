<template>
  <div class="enforcement-mode-selector">
    <div class="selector-header">
      <h3><i class="fas fa-shield-alt"></i> Enforcement Mode</h3>
      <p class="description">
        Control how access control violations are handled across the system
      </p>
    </div>

    <div class="mode-options">
      <div
        v-for="option in modeOptions"
        :key="option.value"
        class="mode-option"
        :class="{
          active: currentMode === option.value,
          updating: loading && pendingMode === option.value
        }"
        @click="selectMode(option.value)"
      >
        <div class="option-icon" :class="option.value">
          <i :class="option.icon"></i>
        </div>
        <div class="option-content">
          <div class="option-header">
            <span class="option-title">{{ option.label }}</span>
            <span v-if="currentMode === option.value" class="current-badge">Current</span>
            <LoadingSpinner v-if="loading && pendingMode === option.value" size="sm" />
          </div>
          <p class="option-description">{{ option.description }}</p>
          <div class="option-details">
            <span
              v-for="(detail, index) in option.details"
              :key="index"
              class="detail-item"
              :class="detail.type"
            >
              <i :class="detail.icon"></i>
              {{ detail.text }}
            </span>
          </div>
        </div>
        <div class="option-radio">
          <div class="radio-outer">
            <div class="radio-inner" v-if="currentMode === option.value"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="mode-warning" v-if="currentMode === 'enforced'">
      <i class="fas fa-exclamation-triangle"></i>
      <div class="warning-content">
        <strong>Full Enforcement Active</strong>
        <p>Unauthorized access attempts will be blocked. Ensure your access control rules are correctly configured.</p>
      </div>
    </div>

    <div class="mode-info" v-if="currentMode === 'log_only'">
      <i class="fas fa-info-circle"></i>
      <div class="info-content">
        <strong>Log-Only Mode</strong>
        <p>Violations are being logged but not blocked. Review the Access Metrics to ensure rules are working correctly before enabling enforcement.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

const props = defineProps<{
  currentMode: EnforcementMode;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:mode', mode: EnforcementMode): void;
}>();

const pendingMode = ref<EnforcementMode | null>(null);

const modeOptions = [
  {
    value: 'disabled' as EnforcementMode,
    label: 'Disabled',
    icon: 'fas fa-ban',
    description: 'Access control is completely disabled. No validation or logging occurs.',
    details: [
      { type: 'neutral', icon: 'fas fa-times', text: 'No validation' },
      { type: 'neutral', icon: 'fas fa-times', text: 'No logging' },
      { type: 'neutral', icon: 'fas fa-times', text: 'No blocking' },
    ],
  },
  {
    value: 'log_only' as EnforcementMode,
    label: 'Log Only',
    icon: 'fas fa-clipboard-list',
    description: 'Violations are validated and logged, but access is not blocked. Ideal for testing.',
    details: [
      { type: 'success', icon: 'fas fa-check', text: 'Validates requests' },
      { type: 'success', icon: 'fas fa-check', text: 'Logs violations' },
      { type: 'warning', icon: 'fas fa-times', text: 'Does not block' },
    ],
  },
  {
    value: 'enforced' as EnforcementMode,
    label: 'Enforced',
    icon: 'fas fa-shield-alt',
    description: 'Full enforcement mode. Unauthorized access attempts are blocked and logged.',
    details: [
      { type: 'success', icon: 'fas fa-check', text: 'Validates requests' },
      { type: 'success', icon: 'fas fa-check', text: 'Logs violations' },
      { type: 'error', icon: 'fas fa-ban', text: 'Blocks unauthorized' },
    ],
  },
];

const selectMode = (mode: EnforcementMode) => {
  if (mode === props.currentMode || props.loading) return;
  pendingMode.value = mode;
  emit('update:mode', mode);
};
</script>

<style scoped>
.enforcement-mode-selector {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.selector-header {
  margin-bottom: 20px;
}

.selector-header h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.selector-header h3 i {
  color: var(--color-primary);
}

.selector-header .description {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

.mode-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mode-option {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-option:hover:not(.updating) {
  border-color: var(--color-primary);
}

.mode-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.mode-option.updating {
  opacity: 0.7;
  cursor: wait;
}

.option-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.option-icon.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.option-icon.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.option-icon.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.option-content {
  flex: 1;
}

.option-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.option-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.current-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-radius: 4px;
  font-weight: 500;
}

.option-description {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.option-details {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.detail-item.neutral {
  color: var(--text-muted);
}

.detail-item.success {
  color: var(--color-success);
}

.detail-item.warning {
  color: var(--color-warning);
}

.detail-item.error {
  color: var(--color-error);
}

.option-radio {
  display: flex;
  align-items: center;
  padding-top: 12px;
}

.radio-outer {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.mode-option.active .radio-outer {
  border-color: var(--color-primary);
}

.radio-inner {
  width: 10px;
  height: 10px;
  background: var(--color-primary);
  border-radius: 50%;
}

.mode-warning,
.mode-info {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding: 14px;
  border-radius: 8px;
}

.mode-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.mode-info {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.mode-warning i,
.mode-info i {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.warning-content strong,
.info-content strong {
  display: block;
  margin-bottom: 4px;
}

.warning-content p,
.info-content p {
  margin: 0;
  font-size: 13px;
  opacity: 0.9;
}
</style>
