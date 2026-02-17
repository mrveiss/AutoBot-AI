<!-- autobot-vue/src/components/profile/ProfileModal.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div v-if="isOpen" class="modal-overlay" @click="handleClose">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h2>Profile Settings</h2>
        <button @click="handleClose" class="close-button">&times;</button>
      </div>

      <div class="modal-body">
        <!-- User Info Section -->
        <div class="profile-section">
          <h3>Account Information</h3>
          <div class="info-grid">
            <div class="info-row">
              <label>Username:</label>
              <span>{{ currentUser?.username || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Email:</label>
              <span>{{ currentUser?.email || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Last Login:</label>
              <span>{{ formatDate(currentUser?.lastLoginAt) }}</span>
            </div>
          </div>
        </div>

        <!-- Password Change Section -->
        <div class="profile-section">
          <h3>Change Password</h3>
          <PasswordChangeForm
            v-if="currentUser?.id"
            :user-id="currentUser.id"
            :require-current-password="true"
            @success="handlePasswordChanged"
            @error="handleError"
          />
        </div>
      </div>

      <!-- Success Toast -->
      <div v-if="successMessage" class="toast success">
        {{ successMessage }}
      </div>

      <!-- Error Toast -->
      <div v-if="errorMessage" class="toast error">
        {{ errorMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'
import { useUserStore } from '@/stores/useUserStore'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const userStore = useUserStore()
const currentUser = computed(() => userStore.currentUser)
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

function handleClose(): void {
  emit('close')
}

function handlePasswordChanged(): void {
  successMessage.value = 'Password changed successfully. Other sessions have been logged out.'
  setTimeout(() => { successMessage.value = null }, 5000)
}

function handleError(error: string): void {
  errorMessage.value = error
  setTimeout(() => { errorMessage.value = null }, 5000)
}

function formatDate(dateValue: Date | string | undefined | null): string {
  if (!dateValue) return 'Never'
  const date = dateValue instanceof Date ? dateValue : new Date(dateValue)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-card);
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-button {
  background: none;
  border: none;
  font-size: 32px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-button:hover {
  background: var(--bg-secondary);
}

.modal-body {
  padding: 24px;
}

.profile-section {
  margin-bottom: 32px;
}

.profile-section:last-child {
  margin-bottom: 0;
}

.profile-section h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.info-row label {
  font-weight: 500;
  color: var(--text-muted);
}

.info-row span {
  color: var(--text-primary);
}

.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  font-weight: 500;
  animation: slideIn 0.3s ease-out;
  z-index: 1100;
}

.toast.success {
  background: #10b981;
  color: white;
}

.toast.error {
  background: #ef4444;
  color: white;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
