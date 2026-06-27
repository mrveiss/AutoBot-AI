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

      <!-- Sub-navigation: switch between Secrets and LLM API Keys -->
      <nav class="secrets-tabs" :aria-label="$t('views.secrets.tabsLabel')">
        <router-link
          :to="{ name: 'secrets-manager' }"
          class="secrets-tab"
          active-class="secrets-tab--active"
          exact-active-class="secrets-tab--active"
        >
          {{ $t('nav.secrets') }}
        </router-link>
        <router-link
          v-if="userStore.isAdmin"
          :to="{ name: 'secrets-llm-keys' }"
          class="secrets-tab"
          active-class="secrets-tab--active"
        >
          {{ $t('nav.llmApiKeys') }}
        </router-link>
      </nav>

      <!-- Child views (secrets manager / LLM API keys) -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for secrets management layout
// Issue #753: Design token usage instead of Tailwind utilities
// Issue #10488: Sub-navigation hosts Secrets Manager + LLM API Keys
import Icon from '@/components/ui/Icon.vue'
import { useUserStore } from '@/stores/useUserStore'

// LLM API keys are admin-managed (the /secrets/llm-keys route + backend are
// admin-gated) — only show that tab to admins so non-admins don't see a tab
// that redirects. (#10488)
const userStore = useUserStore()
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

/* ============================================
 * SUB-NAVIGATION TABS
 * ============================================ */

.secrets-tabs {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-xl);
  border-bottom: 1px solid var(--border-default);
}

.secrets-tab {
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color var(--duration-150) ease, border-color var(--duration-150) ease;
}

.secrets-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.secrets-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
</style>
