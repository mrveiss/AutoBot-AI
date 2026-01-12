<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Permission Denied Component

  Displays when user attempts to access a resource without proper permissions.
  Issue #683: Role-Based Component Access
-->

<template>
  <div class="permission-denied">
    <div class="permission-denied__content">
      <div class="permission-denied__icon">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
        </svg>
      </div>

      <h2 class="permission-denied__title">
        {{ title }}
      </h2>

      <p class="permission-denied__message">
        {{ message }}
      </p>

      <div v-if="showDetails && requiredPermission" class="permission-denied__details">
        <p class="permission-denied__required">
          Required permission: <code>{{ requiredPermission }}</code>
        </p>
        <p class="permission-denied__current">
          Your role: <code>{{ currentRole }}</code>
        </p>
      </div>

      <div class="permission-denied__actions">
        <button
          v-if="showBackButton"
          class="permission-denied__button permission-denied__button--secondary"
          @click="goBack"
        >
          Go Back
        </button>
        <button
          v-if="showHomeButton"
          class="permission-denied__button permission-denied__button--primary"
          @click="goHome"
        >
          Go to Home
        </button>
      </div>

      <p v-if="contactAdmin" class="permission-denied__contact">
        If you believe you should have access, please contact your administrator.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { usePermissions } from '@/composables/usePermissions'

interface Props {
  title?: string
  message?: string
  requiredPermission?: string
  showDetails?: boolean
  showBackButton?: boolean
  showHomeButton?: boolean
  contactAdmin?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Access Denied',
  message: 'You do not have permission to access this resource.',
  requiredPermission: undefined,
  showDetails: false,
  showBackButton: true,
  showHomeButton: true,
  contactAdmin: true,
})

const router = useRouter()
const { role } = usePermissions()

const currentRole = computed(() => role.value)

function goBack(): void {
  router.back()
}

function goHome(): void {
  router.push({ name: 'home' })
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.permission-denied {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  padding: var(--spacing-8);
}

.permission-denied__content {
  max-width: 480px;
  text-align: center;
}

.permission-denied__icon {
  width: 80px;
  height: 80px;
  margin: 0 auto var(--spacing-6);
  color: var(--color-error);
}

.permission-denied__icon svg {
  width: 100%;
  height: 100%;
}

.permission-denied__title {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.permission-denied__message {
  margin: 0 0 var(--spacing-6);
  font-size: var(--text-base);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.permission-denied__details {
  margin: 0 0 var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  text-align: left;
}

.permission-denied__details p {
  margin: var(--spacing-1) 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.permission-denied__details code {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.permission-denied__actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: center;
  margin-bottom: var(--spacing-6);
}

.permission-denied__button {
  padding: var(--spacing-2-5) var(--spacing-5);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.permission-denied__button--primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
}

.permission-denied__button--primary:hover {
  background: var(--color-primary-hover);
}

.permission-denied__button--secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.permission-denied__button--secondary:hover {
  background: var(--bg-secondary);
}

.permission-denied__contact {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}
</style>
