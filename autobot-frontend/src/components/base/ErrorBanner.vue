<template>
  <Transition name="fade">
    <div
      v-if="visible"
      :class="['error-banner', `error-banner-${variant}`]"
      :role="variant === 'error' ? 'alert' : 'status'"
      :aria-live="variant === 'error' ? 'assertive' : 'polite'"
    >
      <div class="error-banner-content">
        <i :class="['error-banner-icon', iconClass]"></i>
        <div class="error-banner-message">
          <slot>{{ message }}</slot>
        </div>
      </div>
      <BaseButton
        v-if="dismissible"
        variant="ghost"
        size="sm"
        :aria-label="$t('common.dismiss')"
        @click="handleDismiss"
      >
        <i class="fas fa-times"></i>
      </BaseButton>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, useSlots } from 'vue'
import BaseButton from './BaseButton.vue'

interface Props {
  message?: string | null
  variant?: 'error' | 'warning' | 'info'
  dismissible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  message: null,
  variant: 'error',
  dismissible: true
})

const emit = defineEmits<{
  dismiss: []
}>()

const slots = useSlots()

const visible = computed(() => !!slots.default?.() || !!props.message)

const iconClass = computed(() => {
  const variantIconMap: Record<string, string> = {
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
  }
  return variantIconMap[props.variant] || variantIconMap.error
})

const handleDismiss = () => {
  emit('dismiss')
}
</script>

<style scoped>
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  border-radius: var(--radius-default);
  border: 1px solid;
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--text-error);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.error-banner-warning {
  background-color: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--text-warning);
}

.error-banner-info {
  background-color: var(--color-info-bg);
  border-color: var(--color-info-border);
  color: var(--text-info);
}

.error-banner-content {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  flex: 1;
}

.error-banner-icon {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  margin-top: var(--spacing-0);
}

.error-banner-message {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
}

/* Fade transition for banner appearance/dismissal */
.fade-enter-active,
.fade-leave-active {
  transition: all var(--duration-200) var(--ease-in-out);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Responsive adjustments */
@media (max-width: 640px) {
  .error-banner {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-3);
  }

  .error-banner-content {
    width: 100%;
  }
}
</style>
