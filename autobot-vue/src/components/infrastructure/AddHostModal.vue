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

              <!-- SSH User -->
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
                  placeholder="root"
                />
              </div>

              <!-- Authentication Type -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">
                  Authentication Method
                </label>
                <div class="flex space-x-4">
                  <label class="flex items-center">
                    <input
                      v-model="authType"
                      type="radio"
                      value="key"
                      class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300"
                    />
                    <span class="ml-2 text-sm text-gray-700">SSH Key</span>
                  </label>
                  <label class="flex items-center">
                    <input
                      v-model="authType"
                      type="radio"
                      value="password"
                      class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300"
                    />
                    <span class="ml-2 text-sm text-gray-700">Password</span>
                  </label>
                </div>
              </div>

              <!-- SSH Key Path (if key auth) -->
              <div v-if="authType === 'key'">
                <label for="ssh_key_path" class="block text-sm font-medium text-gray-700 mb-1">
                  SSH Key Path
                </label>
                <input
                  v-model="formData.ssh_key_path"
                  type="text"
                  id="ssh_key_path"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="~/.ssh/id_rsa"
                />
                <p class="mt-1 text-xs text-gray-500">Leave empty to use default SSH key</p>
              </div>

              <!-- SSH Password (if password auth) -->
              <div v-if="authType === 'password'">
                <label for="ssh_password" class="block text-sm font-medium text-gray-700 mb-1">
                  SSH Password
                </label>
                <input
                  v-model="formData.ssh_password"
                  type="password"
                  id="ssh_password"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="••••••••"
                />
              </div>

              <!-- Description -->
              <div>
                <label for="description" class="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  v-model="formData.description"
                  id="description"
                  rows="2"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="Production web server"
                ></textarea>
              </div>

              <!-- Ansible Group -->
              <div>
                <label for="ansible_group" class="block text-sm font-medium text-gray-700 mb-1">
                  Ansible Group
                </label>
                <input
                  v-model="formData.ansible_group"
                  type="text"
                  id="ansible_group"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="webservers"
                />
              </div>

              <!-- Tags -->
              <div>
                <label for="tags" class="block text-sm font-medium text-gray-700 mb-1">
                  Tags
                </label>
                <input
                  v-model="tagsInput"
                  type="text"
                  id="tags"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="production, web, nginx (comma-separated)"
                />
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
import { ref, defineProps, defineEmits, watch } from 'vue'

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: [formData: Record<string, any>]
}>()

const authType = ref<'key' | 'password'>('key')
const tagsInput = ref('')
const isSubmitting = ref(false)

const formData = ref({
  hostname: '',
  ip_address: '',
  ssh_user: '',
  ssh_key_path: '',
  ssh_password: '',
  description: '',
  ansible_group: '',
  tags: [] as string[]
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
    ssh_user: '',
    ssh_key_path: '',
    ssh_password: '',
    description: '',
    ansible_group: '',
    tags: []
  }
  tagsInput.value = ''
  authType.value = 'key'
}

async function handleSubmit() {
  isSubmitting.value = true

  try {
    // Parse tags
    const tags = tagsInput.value
      .split(',')
      .map(t => t.trim())
      .filter(t => t.length > 0)

    // Prepare form data
    const submitData = {
      ...formData.value,
      tags
    }

    // Remove empty/unused fields
    if (authType.value === 'key') {
      delete submitData.ssh_password
    } else {
      delete submitData.ssh_key_path
    }

    emit('submit', submitData)
    resetForm()
  } catch (error) {
    console.error('Error submitting form:', error)
  } finally {
    isSubmitting.value = false
  }
}
</script>
