<!-- shared-components/PasswordChangeForm.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="password-change-form">
    <!-- Strength Indicator: Color Bar -->
    <div v-if="newPassword" class="strength-indicator">
      <div class="strength-bar" :class="strengthClass">
        <div class="strength-fill" :style="{ width: strengthPercent }"></div>
      </div>
      <span class="strength-label">{{ strengthLabel }}</span>
    </div>

    <!-- Requirements Checklist -->
    <div v-if="newPassword" class="requirements-checklist">
      <div class="requirement" :class="{ met: hasMinLength }">
        <span class="icon">{{ hasMinLength ? '\u2713' : '\u25CB' }}</span>
        At least 8 characters
      </div>
      <div class="requirement" :class="{ met: hasUppercase }">
        <span class="icon">{{ hasUppercase ? '\u2713' : '\u25CB' }}</span>
        One uppercase letter
      </div>
      <div class="requirement" :class="{ met: hasLowercase }">
        <span class="icon">{{ hasLowercase ? '\u2713' : '\u25CB' }}</span>
        One lowercase letter
      </div>
      <div class="requirement" :class="{ met: hasNumber }">
        <span class="icon">{{ hasNumber ? '\u2713' : '\u25CB' }}</span>
        One number
      </div>
    </div>

    <!-- Form Fields -->
    <div class="form-fields">
      <input
        v-if="requireCurrentPassword"
        v-model="currentPassword"
        type="password"
        placeholder="Current Password"
        class="form-input"
        @input="clearError"
      />
      <input
        v-model="newPassword"
        type="password"
        placeholder="New Password"
        class="form-input"
        @input="validateStrength"
      />
      <input
        v-model="confirmPassword"
        type="password"
        placeholder="Confirm Password"
        class="form-input"
        @input="validateMatch"
      />
    </div>

    <!-- Rate Limit Warning -->
    <div v-if="attemptsRemaining !== null && attemptsRemaining <= 1" class="warning">
      {{ attemptsRemaining }} attempt remaining before lockout
    </div>

    <!-- Error Messages -->
    <div v-if="error" class="error">{{ error }}</div>

    <!-- Submit Button -->
    <button
      @click="handleSubmit"
      :disabled="!isValid || loading"
      class="submit-button"
    >
      {{ loading ? 'Changing...' : 'Change Password' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  userId: string
  requireCurrentPassword?: boolean
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

// Default value for optional prop
const requireCurrentPassword = computed(() => props.requireCurrentPassword ?? true)

// Form state
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const attemptsRemaining = ref<number | null>(null)

// Password strength validation
const hasMinLength = computed(() => newPassword.value.length >= 8)
const hasUppercase = computed(() => /[A-Z]/.test(newPassword.value))
const hasLowercase = computed(() => /[a-z]/.test(newPassword.value))
const hasNumber = computed(() => /\d/.test(newPassword.value))

const strengthPercent = computed(() => {
  let score = 0
  if (hasMinLength.value) score += 25
  if (hasUppercase.value) score += 25
  if (hasLowercase.value) score += 25
  if (hasNumber.value) score += 25
  return `${score}%`
})

const strengthClass = computed(() => {
  const score = parseInt(strengthPercent.value)
  if (score === 100) return 'strong'
  if (score >= 50) return 'medium'
  return 'weak'
})

const strengthLabel = computed(() => {
  const score = parseInt(strengthPercent.value)
  if (score === 100) return 'Strong'
  if (score >= 50) return 'Medium'
  return 'Weak'
})

const passwordsMatch = computed(() => {
  return confirmPassword.value === newPassword.value
})

const isValid = computed(() => {
  return hasMinLength.value &&
         hasUppercase.value &&
         hasLowercase.value &&
         hasNumber.value &&
         passwordsMatch.value &&
         (!requireCurrentPassword.value || currentPassword.value)
})

function clearError() {
  error.value = null
}

function validateStrength() {
  clearError()
}

function validateMatch() {
  if (confirmPassword.value && !passwordsMatch.value) {
    error.value = 'Passwords do not match'
  } else {
    clearError()
  }
}

function resetForm() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  attemptsRemaining.value = null
}

async function handleSubmit() {
  if (!isValid.value) return

  loading.value = true
  error.value = null

  try {
    // Get auth token from localStorage or auth store
    const token = localStorage.getItem('authToken') || ''

    const response = await fetch(`/api/users/${props.userId}/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        current_password: requireCurrentPassword.value ? currentPassword.value : null,
        new_password: newPassword.value
      })
    })

    const data = await response.json()

    if (!response.ok) {
      handleApiError(response.status, data)
      return
    }

    // Success
    emit('success', data.message)
    resetForm()

  } catch {
    error.value = 'Unable to change password. Please try again.'
    emit('error', error.value)
  } finally {
    loading.value = false
  }
}

function handleApiError(status: number, data: { detail?: string; attempts_remaining?: number }) {
  if (status === 429) {
    // Rate limited
    error.value = data.detail || 'Too many attempts. Please try again later.'
  } else if (status === 401) {
    // Wrong current password
    error.value = 'Current password is incorrect'
    attemptsRemaining.value = data.attempts_remaining || null
  } else {
    error.value = data.detail || 'Failed to change password'
  }
  emit('error', error.value as string)
}
</script>

<style scoped>
.password-change-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 400px;
}

.strength-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
}

.strength-bar {
  flex: 1;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  transition: width 0.3s, background-color 0.3s;
}

.strength-bar.weak .strength-fill { background: #ef4444; }
.strength-bar.medium .strength-fill { background: #f59e0b; }
.strength-bar.strong .strength-fill { background: #10b981; }

.strength-label {
  font-size: 14px;
  font-weight: 500;
  min-width: 60px;
}

.strength-bar.weak + .strength-label { color: #ef4444; }
.strength-bar.medium + .strength-label { color: #f59e0b; }
.strength-bar.strong + .strength-label { color: #10b981; }

.requirements-checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.requirement {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #6b7280;
  transition: color 0.2s;
}

.requirement.met {
  color: #10b981;
  font-weight: 500;
}

.requirement .icon {
  font-weight: bold;
  width: 20px;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-input {
  padding: 10px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.warning {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  padding: 10px 14px;
  border-radius: 6px;
  color: #92400e;
  font-size: 14px;
}

.error {
  background: #fee2e2;
  border: 1px solid #ef4444;
  padding: 10px 14px;
  border-radius: 6px;
  color: #991b1b;
  font-size: 14px;
}

.submit-button {
  padding: 10px 20px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.submit-button:hover:not(:disabled) {
  background: #2563eb;
}

.submit-button:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
</style>
