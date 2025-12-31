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
.permission-denied {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  padding: 2rem;
}

.permission-denied__content {
  max-width: 480px;
  text-align: center;
}

.permission-denied__icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 1.5rem;
  color: var(--color-danger, #ef4444);
}

.permission-denied__icon svg {
  width: 100%;
  height: 100%;
}

.permission-denied__title {
  margin: 0 0 0.75rem;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text-primary, #1f2937);
}

.permission-denied__message {
  margin: 0 0 1.5rem;
  font-size: 1rem;
  color: var(--color-text-secondary, #6b7280);
  line-height: 1.5;
}

.permission-denied__details {
  margin: 0 0 1.5rem;
  padding: 1rem;
  background: var(--color-bg-secondary, #f3f4f6);
  border-radius: 8px;
  text-align: left;
}

.permission-denied__details p {
  margin: 0.25rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}

.permission-denied__details code {
  padding: 0.125rem 0.375rem;
  background: var(--color-bg-tertiary, #e5e7eb);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8125rem;
  color: var(--color-text-primary, #1f2937);
}

.permission-denied__actions {
  display: flex;
  gap: 0.75rem;
  justify-content: center;
  margin-bottom: 1.5rem;
}

.permission-denied__button {
  padding: 0.625rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.permission-denied__button--primary {
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
}

.permission-denied__button--primary:hover {
  background: var(--color-primary-dark, #2563eb);
}

.permission-denied__button--secondary {
  background: transparent;
  color: var(--color-text-secondary, #6b7280);
  border: 1px solid var(--color-border, #d1d5db);
}

.permission-denied__button--secondary:hover {
  background: var(--color-bg-secondary, #f3f4f6);
}

.permission-denied__contact {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--color-text-muted, #9ca3af);
}

/* Dark mode */
:global(.dark) .permission-denied__title {
  color: var(--color-text-primary-dark, #f3f4f6);
}

:global(.dark) .permission-denied__details {
  background: var(--color-bg-secondary-dark, #374151);
}

:global(.dark) .permission-denied__details code {
  background: var(--color-bg-tertiary-dark, #4b5563);
  color: var(--color-text-primary-dark, #f3f4f6);
}
</style>
