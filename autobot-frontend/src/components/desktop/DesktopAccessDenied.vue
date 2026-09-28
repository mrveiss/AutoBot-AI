<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Shown where a desktop viewer would be, to a caller the socket will refuse
  (#17370). One component rather than the message repeated at each of the four
  render sites.

  This is NOT the access boundary -- `enforce_ws_desktop_auth` is, and #17369
  closed it. This exists so a refused caller reads an explanation instead of a
  viewer that never connects, or a control that silently is not there.
-->
<template>
  <div class="desktop-denied" role="status">
    <Icon name="lock" class="desktop-denied-icon" />
    <p class="desktop-denied-title">{{ t('desktop.accessDenied.title') }}</p>
    <p class="desktop-denied-desc">{{ t('desktop.accessDenied.description') }}</p>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
</script>

<style scoped>
.desktop-denied {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-6);
  text-align: center;
}

.desktop-denied-icon {
  font-size: var(--text-3xl);
  color: var(--color-text-secondary);
}

.desktop-denied-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.desktop-denied-desc {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  max-width: 42ch;
}
</style>
