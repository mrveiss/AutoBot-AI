<template>
  <div class="permission-denied-view view-container-centered">
    <PermissionDenied
      :title="title"
      :message="message"
      :required-permission="requiredPermission"
      :show-details="showDetails"
      :show-back-button="showBackButton"
      :show-home-button="showHomeButton"
      :contact-admin="contactAdmin"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Permission Denied View
 *
 * Displays when a user attempts to access a resource or feature without
 * the required permissions. This is a page-level container that wraps
 * the PermissionDenied component.
 *
 * Issue #4279: Wire orphaned PermissionDenied component
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PermissionDenied from '@/components/common/PermissionDenied.vue'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const { t } = useI18n()

/**
 * Extract permission details from route query parameters
 * e.g., /permission-denied?required=admin:access&current=user
 */
const title = computed(() => {
  return route.query.title as string || t('common.permissionDenied.title')
})

const message = computed(() => {
  return route.query.message as string || t('common.permissionDenied.message')
})

const requiredPermission = computed(() => {
  return route.query.required as string || undefined
})

const showDetails = computed(() => {
  return route.query.details === 'true'
})

const showBackButton = computed(() => {
  const val = route.query.back as string | undefined
  return val === 'false' ? false : true
})

const showHomeButton = computed(() => {
  const val = route.query.home as string | undefined
  return val === 'false' ? false : true
})

const contactAdmin = computed(() => {
  const val = route.query.admin as string | undefined
  return val === 'false' ? false : true
})
</script>

<style scoped>
/* Permission Denied View Container */
.permission-denied-view {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  /* #10750 C2: .view-container-centered already clamps to viewport-header */
  min-height: 100%;
  background: var(--bg-primary);
}
</style>
