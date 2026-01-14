<template>
  <BaseModal
    v-model="modelVisible"
    title="Add New Node"
    size="large"
    :closeOnOverlay="!isSubmitting"
  >
    <div class="add-node-modal">
      <!-- Connection Info Section -->
      <div class="form-section">
        <h5 class="section-title">
          <i class="fas fa-network-wired"></i>
          Connection Information
        </h5>

        <div class="form-row">
          <div class="form-group flex-2">
            <label for="hostname">
              Hostname <span class="required">*</span>
            </label>
            <input
              v-model="formData.hostname"
              type="text"
              id="hostname"
              placeholder="e.g., npu-worker-02"
              :class="{ error: errors.hostname }"
              @blur="validateField('hostname')"
            />
            <span v-if="errors.hostname" class="error-text">{{ errors.hostname }}</span>
          </div>

          <div class="form-group flex-2">
            <label for="ip_address">
              IP Address <span class="required">*</span>
            </label>
            <input
              v-model="formData.ip_address"
              type="text"
              id="ip_address"
              placeholder="e.g., 172.16.168.26"
              :class="{ error: errors.ip_address }"
              @blur="validateField('ip_address')"
            />
            <span v-if="errors.ip_address" class="error-text">{{ errors.ip_address }}</span>
          </div>

          <div class="form-group flex-1">
            <label for="ssh_port">SSH Port</label>
            <input
              v-model.number="formData.ssh_port"
              type="number"
              id="ssh_port"
              min="1"
              max="65535"
            />
          </div>
        </div>
      </div>

      <!-- Authentication Section -->
      <div class="form-section">
        <h5 class="section-title">
          <i class="fas fa-key"></i>
          Authentication Method
        </h5>

        <div class="auth-options">
          <label class="auth-option" :class="{ selected: formData.auth_method === 'password' }">
            <input
              type="radio"
              v-model="formData.auth_method"
              value="password"
            />
            <div class="option-content">
              <i class="fas fa-lock"></i>
              <div>
                <strong>Password</strong>
                <span>Sudo user with password</span>
              </div>
            </div>
          </label>

          <label class="auth-option" :class="{ selected: formData.auth_method === 'pki' }">
            <input
              type="radio"
              v-model="formData.auth_method"
              value="pki"
            />
            <div class="option-content">
              <i class="fas fa-certificate"></i>
              <div>
                <strong>PKI (SSH Key)</strong>
                <span>Recommended for production</span>
              </div>
            </div>
          </label>
        </div>

        <!-- Password Auth Fields -->
        <div v-if="formData.auth_method === 'password'" class="auth-fields">
          <div class="form-row">
            <div class="form-group flex-1">
              <label for="ssh_user">
                Username <span class="required">*</span>
              </label>
              <input
                v-model="formData.ssh_user"
                type="text"
                id="ssh_user"
                placeholder="root or autobot"
              />
            </div>
            <div class="form-group flex-1">
              <label for="password">
                Password <span class="required">*</span>
              </label>
              <div class="password-input">
                <input
                  v-model="formData.password"
                  :type="showPassword ? 'text' : 'password'"
                  id="password"
                  placeholder="Enter password"
                  :class="{ error: errors.password }"
                />
                <button type="button" @click="showPassword = !showPassword" class="toggle-password">
                  <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                </button>
              </div>
              <span v-if="errors.password" class="error-text">{{ errors.password }}</span>
            </div>
          </div>
          <div class="form-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="formData.has_sudo" />
              User has sudo privileges
            </label>
          </div>
        </div>

        <!-- PKI Auth Fields -->
        <div v-if="formData.auth_method === 'pki'" class="auth-fields">
          <div class="form-row">
            <div class="form-group flex-1">
              <label for="ssh_user_pki">
                Username <span class="required">*</span>
              </label>
              <input
                v-model="formData.ssh_user"
                type="text"
                id="ssh_user_pki"
                placeholder="autobot"
              />
            </div>
          </div>

          <div class="form-group">
            <label>SSH Key</label>
            <div class="key-options">
              <label class="key-option" :class="{ selected: keySource === 'default' }">
                <input type="radio" v-model="keySource" value="default" />
                <span>Use default key (~/.ssh/autobot_key)</span>
              </label>
              <label class="key-option" :class="{ selected: keySource === 'browse' }">
                <input type="radio" v-model="keySource" value="browse" />
                <span>Browse for key file</span>
              </label>
              <label class="key-option" :class="{ selected: keySource === 'paste' }">
                <input type="radio" v-model="keySource" value="paste" />
                <span>Paste key content</span>
              </label>
            </div>
          </div>

          <div v-if="keySource === 'browse'" class="form-group">
            <label for="key_path">Key Path</label>
            <input
              v-model="formData.ssh_key_path"
              type="text"
              id="key_path"
              placeholder="/path/to/private_key"
            />
          </div>

          <div v-if="keySource === 'paste'" class="form-group">
            <label for="ssh_key">SSH Private Key</label>
            <textarea
              v-model="formData.ssh_key"
              id="ssh_key"
              rows="6"
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----"
              :class="{ error: errors.ssh_key }"
            ></textarea>
            <span v-if="errors.ssh_key" class="error-text">{{ errors.ssh_key }}</span>
          </div>
        </div>
      </div>

      <!-- Role Assignment Section -->
      <div class="form-section">
        <h5 class="section-title">
          <i class="fas fa-user-tag"></i>
          Role Assignment
        </h5>

        <div class="form-group">
          <label for="role">
            Node Role <span class="required">*</span>
          </label>
          <select
            v-model="formData.role"
            id="role"
            :class="{ error: errors.role }"
          >
            <option value="" disabled>Select a role</option>
            <option
              v-for="role in availableRoles"
              :key="role.id"
              :value="role.id"
            >
              {{ role.name }} - {{ role.description }}
            </option>
          </select>
          <span v-if="errors.role" class="error-text">{{ errors.role }}</span>
        </div>

        <!-- Role Details -->
        <div v-if="selectedRoleDetails" class="role-details">
          <div class="role-info">
            <span class="info-label">Services:</span>
            <span class="info-value">{{ selectedRoleDetails.services.join(', ') || 'None' }}</span>
          </div>
          <div v-if="selectedRoleDetails.default_port" class="role-info">
            <span class="info-label">Default Port:</span>
            <span class="info-value">{{ selectedRoleDetails.default_port }}</span>
          </div>
        </div>
      </div>

      <!-- Enrollment Options -->
      <div class="form-section">
        <h5 class="section-title">
          <i class="fas fa-cog"></i>
          Enrollment Options
        </h5>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.auto_enroll" />
            Start enrollment immediately after adding
          </label>
          <p class="help-text">
            If enabled, the node will be automatically enrolled with Ansible after being added.
            This includes installing dependencies, deploying certificates, and configuring services.
          </p>
        </div>
      </div>

      <!-- Connection Test Result -->
      <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
        <i :class="testResult.success ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>
        <div>
          <strong>{{ testResult.success ? 'Connection Successful' : 'Connection Failed' }}</strong>
          <p>{{ testResult.message }}</p>
        </div>
      </div>
    </div>

    <template #actions>
      <button @click="closeModal" class="cancel-btn" :disabled="isSubmitting">
        Cancel
      </button>
      <button
        @click="testConnection"
        class="test-btn"
        :disabled="!canTest || isTesting"
      >
        <i :class="isTesting ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
        {{ isTesting ? 'Testing...' : 'Test Connection' }}
      </button>
      <button
        @click="submitForm"
        class="submit-btn"
        :disabled="!canSubmit || isSubmitting"
      >
        <i :class="isSubmitting ? 'fas fa-spinner fa-spin' : 'fas fa-plus'"></i>
        {{ isSubmitting ? 'Adding...' : 'Add Node' }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('AddNodeModal')

// Types
interface NodeRole {
  id: string
  name: string
  description: string
  services: string[]
  default_port?: number
}

interface FormData {
  hostname: string
  ip_address: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  ssh_user: string
  password: string
  has_sudo: boolean
  ssh_key: string
  ssh_key_path: string
  role: string
  auto_enroll: boolean
}

interface TestResult {
  success: boolean
  message: string
}

// Props
interface Props {
  visible: boolean
  availableRoles: NodeRole[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
  submit: [data: {
    hostname: string
    ip_address: string
    ssh_user: string
    ssh_port: number
    auth_method: 'password' | 'pki'
    password?: string
    ssh_key?: string
    role: string
    auto_enroll: boolean
  }]
}>()

// State
const modelVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const formData = ref<FormData>({
  hostname: '',
  ip_address: '',
  ssh_port: 22,
  auth_method: 'password',
  ssh_user: 'autobot',
  password: '',
  has_sudo: true,
  ssh_key: '',
  ssh_key_path: '',
  role: '',
  auto_enroll: true,
})

const errors = ref<Record<string, string>>({})
const showPassword = ref(false)
const keySource = ref<'default' | 'browse' | 'paste'>('default')
const isTesting = ref(false)
const isSubmitting = ref(false)
const testResult = ref<TestResult | null>(null)

// Computed
const selectedRoleDetails = computed(() => {
  if (!formData.value.role) return null
  return props.availableRoles.find(r => r.id === formData.value.role)
})

const canTest = computed(() => {
  return formData.value.hostname &&
         formData.value.ip_address &&
         formData.value.ssh_user &&
         (formData.value.auth_method === 'pki' ||
          (formData.value.auth_method === 'password' && formData.value.password))
})

const canSubmit = computed(() => {
  return canTest.value && formData.value.role && Object.keys(errors.value).length === 0
})

// Watchers
watch(() => props.visible, (visible) => {
  if (!visible) {
    resetForm()
  }
})

// Methods
function validateField(field: string) {
  const value = formData.value[field as keyof FormData]

  switch (field) {
    case 'hostname':
      if (!value) {
        errors.value.hostname = 'Hostname is required'
      } else if (!/^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$/.test(value as string)) {
        errors.value.hostname = 'Invalid hostname format'
      } else {
        delete errors.value.hostname
      }
      break

    case 'ip_address':
      if (!value) {
        errors.value.ip_address = 'IP address is required'
      } else if (!/^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/.test(value as string)) {
        errors.value.ip_address = 'Invalid IPv4 address'
      } else {
        delete errors.value.ip_address
      }
      break

    case 'password':
      if (formData.value.auth_method === 'password' && !value) {
        errors.value.password = 'Password is required'
      } else {
        delete errors.value.password
      }
      break

    case 'ssh_key':
      if (formData.value.auth_method === 'pki' && keySource.value === 'paste' && !value) {
        errors.value.ssh_key = 'SSH key is required'
      } else {
        delete errors.value.ssh_key
      }
      break

    case 'role':
      if (!value) {
        errors.value.role = 'Role is required'
      } else {
        delete errors.value.role
      }
      break
  }
}

function validateAll(): boolean {
  validateField('hostname')
  validateField('ip_address')
  validateField('role')

  if (formData.value.auth_method === 'password') {
    validateField('password')
  } else if (keySource.value === 'paste') {
    validateField('ssh_key')
  }

  return Object.keys(errors.value).length === 0
}

async function testConnection() {
  if (!canTest.value) return

  isTesting.value = true
  testResult.value = null

  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ip_address: formData.value.ip_address,
        ssh_port: formData.value.ssh_port,
        ssh_user: formData.value.ssh_user,
        auth_method: formData.value.auth_method,
        password: formData.value.auth_method === 'password' ? formData.value.password : undefined,
        ssh_key: getSshKey(),
      }),
    })

    const result = await response.json()

    testResult.value = {
      success: result.success,
      message: result.success
        ? `Successfully connected to ${formData.value.ip_address}. OS: ${result.os || 'Unknown'}`
        : result.error || 'Connection failed',
    }
  } catch (error) {
    logger.error('Connection test error:', error)
    testResult.value = {
      success: false,
      message: 'Failed to test connection. Please check your network.',
    }
  } finally {
    isTesting.value = false
  }
}

function getSshKey(): string | undefined {
  if (formData.value.auth_method !== 'pki') return undefined

  switch (keySource.value) {
    case 'default':
      return undefined  // Backend will use default
    case 'browse':
      return formData.value.ssh_key_path
    case 'paste':
      return formData.value.ssh_key
    default:
      return undefined
  }
}

async function submitForm() {
  if (!validateAll()) return

  isSubmitting.value = true

  try {
    emit('submit', {
      hostname: formData.value.hostname,
      ip_address: formData.value.ip_address,
      ssh_user: formData.value.ssh_user,
      ssh_port: formData.value.ssh_port,
      auth_method: formData.value.auth_method,
      password: formData.value.auth_method === 'password' ? formData.value.password : undefined,
      ssh_key: getSshKey(),
      role: formData.value.role,
      auto_enroll: formData.value.auto_enroll,
    })

    closeModal()
  } catch (error) {
    logger.error('Submit error:', error)
  } finally {
    isSubmitting.value = false
  }
}

function closeModal() {
  emit('close')
}

function resetForm() {
  formData.value = {
    hostname: '',
    ip_address: '',
    ssh_port: 22,
    auth_method: 'password',
    ssh_user: 'autobot',
    password: '',
    has_sudo: true,
    ssh_key: '',
    ssh_key_path: '',
    role: '',
    auto_enroll: true,
  }
  errors.value = {}
  testResult.value = null
  showPassword.value = false
  keySource.value = 'default'
}
</script>

<style scoped>
.add-node-modal {
  max-height: 70vh;
  overflow-y: auto;
}

/* Form Sections */
.form-section {
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border-light);
}

.form-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-title i {
  color: var(--color-primary);
}

/* Form Layout */
.form-row {
  display: flex;
  gap: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group.flex-1 {
  flex: 1;
}

.form-group.flex-2 {
  flex: 2;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-danger);
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group input[type="password"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-bg);
}

.form-group input.error,
.form-group select.error,
.form-group textarea.error {
  border-color: var(--color-danger);
}

.error-text {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-danger);
}

.help-text {
  margin: 8px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* Password Input */
.password-input {
  position: relative;
}

.password-input input {
  padding-right: 40px;
}

.toggle-password {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
}

.toggle-password:hover {
  color: var(--text-primary);
}

/* Auth Options */
.auth-options {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.auth-option {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 16px;
  border: 2px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.auth-option:hover {
  border-color: var(--color-primary);
  background: var(--bg-secondary);
}

.auth-option.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.auth-option input {
  display: none;
}

.option-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.option-content i {
  font-size: 24px;
  color: var(--color-primary);
}

.option-content strong {
  display: block;
  font-size: 14px;
  color: var(--text-primary);
}

.option-content span {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Auth Fields */
.auth-fields {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

/* Key Options */
.key-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.key-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.key-option:hover {
  background: var(--bg-tertiary);
}

.key-option.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.key-option input {
  accent-color: var(--color-primary);
}

/* Checkbox Label */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.checkbox-label input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

/* Role Details */
.role-details {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.role-info {
  display: flex;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 4px;
}

.role-info:last-child {
  margin-bottom: 0;
}

.info-label {
  color: var(--text-tertiary);
}

.info-value {
  color: var(--text-primary);
}

/* Test Result */
.test-result {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 6px;
  margin-top: 16px;
}

.test-result.success {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
}

.test-result.success i {
  color: var(--color-success);
}

.test-result.error {
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger);
}

.test-result.error i {
  color: var(--color-danger);
}

.test-result i {
  font-size: 20px;
  margin-top: 2px;
}

.test-result strong {
  display: block;
  margin-bottom: 4px;
}

.test-result p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

/* Modal Actions */
.cancel-btn {
  padding: 10px 16px;
  background: var(--text-tertiary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.test-btn {
  padding: 10px 16px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.test-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
}

.submit-btn {
  padding: 10px 20px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.submit-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.cancel-btn:disabled,
.test-btn:disabled,
.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
  }

  .auth-options {
    flex-direction: column;
  }
}
</style>
