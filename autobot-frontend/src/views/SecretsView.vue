<template>
  <div class="secrets-view view-container">
    <div class="secrets-content">
      <!-- Security notice -->
      <div class="security-notice">
        <div class="notice-inner">
          <i class="fas fa-shield-alt notice-icon"></i>
          <div class="notice-content">
            <h3 class="notice-title">Security Notice</h3>
            <p class="notice-text">
              All secrets are encrypted and stored securely. Never share your API keys or access tokens.
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
  background: rgba(245, 158, 11, 0.1); /* Warning background */
  border: 1px solid var(--color-warning-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.notice-inner {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.notice-icon {
  font-size: var(--font-size-lg);
  color: var(--color-warning);
  flex-shrink: 0;
  margin-top: 2px;
}

.notice-content {
  flex: 1;
}

.notice-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-warning-dark);
  margin: 0 0 var(--spacing-xs) 0;
}

.notice-text {
  font-size: var(--font-size-sm);
  color: var(--color-warning-dark);
  margin: 0;
  line-height: var(--line-height-relaxed);
}

/* Dark mode adjustments */
[data-theme="dark"] .security-notice {
  background: rgba(245, 158, 11, 0.15);
  border-color: var(--color-warning);
}

[data-theme="dark"] .notice-title,
[data-theme="dark"] .notice-text {
  color: var(--color-warning-light);
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .secrets-content {
    padding: var(--spacing-sm);
  }

  .security-notice {
    padding: var(--spacing-sm);
  }

  .notice-inner {
    gap: var(--spacing-sm);
  }
}
</style>
