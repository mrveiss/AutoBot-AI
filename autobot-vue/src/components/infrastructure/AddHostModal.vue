<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="visible"
        class="fixed inset-0 z-50 overflow-y-auto"
        @click.self="$emit('close')"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <!-- Background overlay -->
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"></div>

          <!-- Modal panel -->
          <div
            @click.stop
            class="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <h3 class="text-lg font-medium text-gray-900">Add New Host</h3>
              <button
                @click="$emit('close')"
                class="rounded-md text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Form -->
            <form @submit.prevent="handleSubmit" class="space-y-4">
              <!-- Hostname -->
              <div>
                <label for="hostname" class="block text-sm font-medium text-gray-700 mb-1">
                  Hostname <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="formData.hostname"
                  type="text"
                  id="hostname"
                  required
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="web-server-01"
                />
              </div>

              <!-- IP Address -->
              <div>
                <label for="ip_address" class="block text-sm font-medium text-gray-700 mb-1">
                  IP Address <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="formData.ip_address"
                  type="text"
                  id="ip_address"
                  required
                  pattern="^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="192.168.1.100"
                />
              </div>

              <!-- SSH User and Port -->
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label for="ssh_user" class="block text-sm font-medium text-gray-700 mb-1">
                    SSH User <span class="text-red-500">*</span>
                  </label>
                  <input
                    v-model="formData.ssh_user"
                    type="text"
                    id="ssh_user"
                    required
                    class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    placeholder="autobot"
                  />
                </div>
                <div>
                  <label for="ssh_port" class="block text-sm font-medium text-gray-700 mb-1">
                    SSH Port
                  </label>
                  <input
                    v-model.number="formData.ssh_port"
                    type="number"
                    id="ssh_port"
                    min="1"
                    max="65535"
                    class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    placeholder="22"
                  />
                </div>
              </div>

              <!-- SSH Password -->
              <div>
                <label for="ssh_password" class="block text-sm font-medium text-gray-700 mb-1">
                  SSH Password <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="formData.ssh_password"
                  type="password"
                  id="ssh_password"
                  required
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="••••••••"
                />
                <p class="mt-1 text-xs text-gray-500">After adding the host, you can provision an SSH key for passwordless access.</p>
              </div>

              <!-- Role (required) -->
              <div>
                <label for="role" class="block text-sm font-medium text-gray-700 mb-1">
                  Role <span class="text-red-500">*</span>
                </label>
                <select
                  v-model="formData.role"
                  id="role"
                  required
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                >
                  <option value="" disabled>Select a role</option>
                  <option v-for="role in availableRoles" :key="role.name" :value="role.name">
                    {{ role.name }} - {{ role.description }}
                  </option>
                </select>
              </div>

              <!-- Actions -->
              <div class="flex items-center justify-end space-x-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  @click="$emit('close')"
                  class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="isSubmitting"
                  class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span v-if="isSubmitting" class="flex items-center">
                    <svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Adding...
                  </span>
                  <span v-else>Add Host</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, watch, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('AddHostModal')

interface Role {
  id: number
  name: string
  description: string
}

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: [formData: FormData]
}>()

const isSubmitting = ref(false)
const availableRoles = ref<Role[]>([])

const formData = ref({
  hostname: '',
  ip_address: '',
  ssh_user: 'autobot',
  ssh_port: 22,
  ssh_password: '',
  role: ''
})

// Fetch available roles
async function fetchRoles() {
  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/iac/roles`)
    if (response.ok) {
      availableRoles.value = await response.json()
    }
  } catch (error) {
    logger.error('Failed to fetch roles:', error)
  }
}

onMounted(() => {
  fetchRoles()
})

// Reset form when modal closes
watch(() => formData.value, () => {
  if (!formData.value) {
    resetForm()
  }
})

function resetForm() {
  formData.value = {
    hostname: '',
    ip_address: '',
    ssh_user: 'autobot',
    ssh_port: 22,
    ssh_password: '',
    role: ''
  }
}

async function handleSubmit() {
  isSubmitting.value = true

  try {
    // Create FormData for multipart submission (required by backend)
    const submitFormData = new FormData()

    // Required fields
    submitFormData.append('hostname', formData.value.hostname)
    submitFormData.append('ip_address', formData.value.ip_address)
    submitFormData.append('role', formData.value.role)
    submitFormData.append('ssh_port', String(formData.value.ssh_port))
    submitFormData.append('ssh_user', formData.value.ssh_user)
    submitFormData.append('auth_method', 'password')
    submitFormData.append('password', formData.value.ssh_password)

    emit('submit', submitFormData)
    resetForm()
  } catch (error) {
    logger.error('Error submitting form:', error)
  } finally {
    isSubmitting.value = false
  }
}
</script>
