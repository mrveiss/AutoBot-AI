<template>
  <div class="enforcement-mode-selector">
    <div class="selector-header">
      <h3><Icon name="shield-alt" /> {{ $t('featureFlags.modeSelector.title') }}</h3>
      <p class="description">
        {{ $t('featureFlags.modeSelector.description') }}
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
          <Icon :name="option.icon" />
        </div>
        <div class="option-content">
          <div class="option-header">
            <span class="option-title">{{ option.label }}</span>
            <span v-if="currentMode === option.value" class="current-badge">{{ $t('featureFlags.modeSelector.current') }}</span>
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
              <Icon :name="detail.icon" />
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
      <Icon name="exclamation-triangle" />
      <div class="warning-content">
        <strong>{{ $t('featureFlags.modeSelector.warningTitle') }}</strong>
        <p>{{ $t('featureFlags.modeSelector.warningDesc') }}</p>
      </div>
    </div>

    <div class="mode-info" v-if="currentMode === 'log_only'">
      <Icon name="info-circle" />
      <div class="info-content">
        <strong>{{ $t('featureFlags.modeSelector.infoTitle') }}</strong>
        <p>{{ $t('featureFlags.modeSelector.infoDesc') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

const { t } = useI18n();

const props = defineProps<{
  currentMode: EnforcementMode;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:mode', mode: EnforcementMode): void;
}>();

const pendingMode = ref<EnforcementMode | null>(null);

const modeOptions = computed(() => [
  {
    value: 'disabled' as EnforcementMode,
    label: t('featureFlags.modeSelector.modeDisabled'),
    icon: 'ban',
    description: t('featureFlags.modeSelector.modeDisabledDesc'),
    details: [
      { type: 'neutral', icon: 'times', text: t('featureFlags.modeSelector.modeDisabledDetail1') },
      { type: 'neutral', icon: 'times', text: t('featureFlags.modeSelector.modeDisabledDetail2') },
      { type: 'neutral', icon: 'times', text: t('featureFlags.modeSelector.modeDisabledDetail3') },
    ],
  },
  {
    value: 'log_only' as EnforcementMode,
    label: t('featureFlags.modeSelector.modeLogOnly'),
    icon: 'clipboard-list',
    description: t('featureFlags.modeSelector.modeLogOnlyDesc'),
    details: [
      { type: 'success', icon: 'check', text: t('featureFlags.modeSelector.modeLogOnlyDetail1') },
      { type: 'success', icon: 'check', text: t('featureFlags.modeSelector.modeLogOnlyDetail2') },
      { type: 'warning', icon: 'times', text: t('featureFlags.modeSelector.modeLogOnlyDetail3') },
    ],
  },
  {
    value: 'enforced' as EnforcementMode,
    label: t('featureFlags.modeSelector.modeEnforced'),
    icon: 'shield-alt',
    description: t('featureFlags.modeSelector.modeEnforcedDesc'),
    details: [
      { type: 'success', icon: 'check', text: t('featureFlags.modeSelector.modeEnforcedDetail1') },
      { type: 'success', icon: 'check', text: t('featureFlags.modeSelector.modeEnforcedDetail2') },
      { type: 'error', icon: 'ban', text: t('featureFlags.modeSelector.modeEnforcedDetail3') },
    ],
  },
]);

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
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.selector-header {
  margin-bottom: var(--spacing-5);
}

.selector-header h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.selector-header h3 i {
  color: var(--color-primary);
}

.selector-header .description {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.mode-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.mode-option {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
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
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
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
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-1);
}

.option-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.current-badge {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-radius: var(--radius-default);
  font-weight: 500;
}

.option-description {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2-5);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.4;
}

.option-details {
  display: flex;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
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
  padding-top: var(--spacing-3);
}

.radio-outer {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
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
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
  padding: var(--spacing-3-5);
  border-radius: var(--radius-lg);
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
  font-size: var(--text-lg);
  flex-shrink: 0;
  margin-top: var(--spacing-0-5);
}

.warning-content strong,
.info-content strong {
  display: block;
  margin-bottom: var(--spacing-1);
}

.warning-content p,
.info-content p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  opacity: 0.9;
}
</style>
