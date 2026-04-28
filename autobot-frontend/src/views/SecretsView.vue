<template>
  <div class="secrets-view view-container">
    <div class="secrets-content">
      <!-- Security notice -->
      <div class="security-notice">
        <div class="notice-inner">
          <Icon name="shield-alt" class="notice-icon" />
          <div class="notice-content">
            <h3 class="notice-title">{{ $t('views.secrets.noticeTitle') }}</h3>
            <p class="notice-text">
              {{ $t('views.secrets.noticeText') }}
            </p>
          </div>
        </div>
      </div>

      <!-- Secrets content will be handled by the existing secrets component -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for secrets management layout
// Issue #753: Design token usage instead of Tailwind utilities
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
</script>

<style scoped>
/* ============================================
 * SECRETS VIEW - Using Design Tokens
 * ============================================ */

.secrets-content {
  width: 100%;
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-xl);
}

/* ============================================
 * SECURITY NOTICE
 * ============================================ */

.security-notice {
  margin-bottom: var(--spacing-xl);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.notice-inner {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.notice-icon {
  font-size: var(--text-lg);
  color: var(--color-warning);
  flex-shrink: 0;
  margin-top: var(--spacing-0-5);
}

.notice-content {
  flex: 1;
}

.notice-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-warning);
  margin: 0 0 var(--spacing-xs) 0;
}

.notice-text {
  font-size: var(--text-sm);
  color: var(--color-warning);
  margin: var(--spacing-0);
}
</style>
