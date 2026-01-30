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
            class="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-2xl sm:p-6"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <div>
                <h3 class="text-lg font-medium text-gray-900">
                  {{ isEditing ? 'Update TLS Certificate' : 'Add TLS Certificate' }}
                </h3>
                <p class="text-sm text-gray-500 mt-1">
                  Upload PEM-encoded certificates for mTLS authentication
                </p>
              </div>
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
              <!-- Credential Name -->
              <div>
                <label for="name" class="block text-sm font-medium text-gray-700 mb-1">
                  Credential Name
                </label>
                <input
                  v-model="formData.name"
                  type="text"
                  id="name"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  placeholder="redis-mtls, api-server-cert"
                />
                <p class="mt-1 text-xs text-gray-500">Optional friendly name for this certificate</p>
              </div>

              <!-- CA Certificate -->
              <div>
                <label for="ca_cert" class="block text-sm font-medium text-gray-700 mb-1">
                  CA Certificate <span class="text-red-500">*</span>
                </label>
                <div class="flex items-center space-x-2 mb-2">
                  <label
                    class="px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100 cursor-pointer"
                  >
                    <input
                      type="file"
                      accept=".pem,.crt,.cer"
                      @change="handleFileUpload('ca_cert', $event)"
                      class="hidden"
                    />
                    Upload File
                  </label>
                  <span class="text-sm text-gray-500">or paste below</span>
                </div>
                <textarea
                  v-model="formData.ca_cert"
                  id="ca_cert"
                  :required="!isEditing"
                  rows="4"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-xs"
                  placeholder="-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----"
                ></textarea>
              </div>

              <!-- Server Certificate -->
              <div>
                <label for="server_cert" class="block text-sm font-medium text-gray-700 mb-1">
                  Server Certificate <span class="text-red-500">*</span>
                </label>
                <div class="flex items-center space-x-2 mb-2">
                  <label
                    class="px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100 cursor-pointer"
                  >
                    <input
                      type="file"
                      accept=".pem,.crt,.cer"
                      @change="handleFileUpload('server_cert', $event)"
                      class="hidden"
                    />
                    Upload File
                  </label>
                  <span class="text-sm text-gray-500">or paste below</span>
                </div>
                <textarea
                  v-model="formData.server_cert"
                  id="server_cert"
                  :required="!isEditing"
                  rows="4"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-xs"
                  placeholder="-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----"
                ></textarea>
              </div>

              <!-- Server Private Key -->
              <div>
                <label for="server_key" class="block text-sm font-medium text-gray-700 mb-1">
                  Server Private Key <span class="text-red-500">*</span>
                </label>
                <div class="flex items-center space-x-2 mb-2">
                  <label
                    class="px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100 cursor-pointer"
                  >
                    <input
                      type="file"
                      accept=".pem,.key"
                      @change="handleFileUpload('server_key', $event)"
                      class="hidden"
                    />
                    Upload File
                  </label>
                  <span class="text-sm text-gray-500">or paste below</span>
                </div>
                <textarea
                  v-model="formData.server_key"
                  id="server_key"
                  :required="!isEditing"
                  rows="4"
                  class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-xs"
                  placeholder="-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----"
                ></textarea>
                <p class="mt-1 text-xs text-red-600">
                  Warning: Private key will be encrypted and stored securely
                </p>
              </div>

              <!-- Active Toggle (for editing) -->
              <div v-if="isEditing" class="flex items-center">
                <input
                  v-model="formData.is_active"
                  type="checkbox"
                  id="is_active"
                  class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                />
                <label for="is_active" class="ml-2 block text-sm text-gray-700">
                  Certificate is active
                </label>
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
                    {{ isEditing ? 'Updating...' : 'Uploading...' }}
                  </span>
                  <span v-else>{{ isEditing ? 'Update Certificate' : 'Upload Certificate' }}</span>
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
/**
 * TLS Credential Modal Component
 *
 * Modal for creating/updating TLS certificates for mTLS authentication.
 * Issue #725: mTLS Migration
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, watch, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import type { TLSCredential, TLSCredentialCreate, TLSCredentialUpdate } from '@/composables/useTLSCredentials'

const logger = createLogger('TLSCredentialModal')

interface Props {
  visible: boolean
  nodeId: string
  credential?: TLSCredential | null
}

const props = withDefaults(defineProps<Props>(), {
  credential: null,
})

const emit = defineEmits<{
  close: []
  submit: [data: TLSCredentialCreate | TLSCredentialUpdate]
}>()

const isSubmitting = ref(false)
const isEditing = computed(() => props.credential !== null)

const formData = ref({
  name: '',
  ca_cert: '',
  server_cert: '',
  server_key: '',
  is_active: true,
})

// Populate form when editing
watch(() => props.credential, (cred) => {
  if (cred) {
    formData.value = {
      name: cred.name || '',
      ca_cert: '',
      server_cert: '',
      server_key: '',
      is_active: cred.is_active,
    }
  } else {
    resetForm()
  }
}, { immediate: true })

// Reset form when modal closes
watch(() => props.visible, (visible) => {
  if (!visible) {
    resetForm()
  }
})

function resetForm() {
  formData.value = {
    name: '',
    ca_cert: '',
    server_cert: '',
    server_key: '',
    is_active: true,
  }
}

async function handleFileUpload(
  field: 'ca_cert' | 'server_cert' | 'server_key',
  event: Event
) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]

  if (!file) return

  try {
    const content = await file.text()
    formData.value[field] = content.trim()
    logger.debug(`Loaded ${field} from file: ${file.name}`)
  } catch (err) {
    logger.error(`Failed to read file for ${field}:`, err)
  }

  // Reset input so same file can be selected again
  input.value = ''
}

async function handleSubmit() {
  isSubmitting.value = true

  try {
    if (isEditing.value) {
      // Build update payload with only changed fields
      const updateData: TLSCredentialUpdate = {}

      if (formData.value.name !== props.credential?.name) {
        updateData.name = formData.value.name || undefined
      }
      if (formData.value.ca_cert) {
        updateData.ca_cert = formData.value.ca_cert
      }
      if (formData.value.server_cert) {
        updateData.server_cert = formData.value.server_cert
      }
      if (formData.value.server_key) {
        updateData.server_key = formData.value.server_key
      }
      if (formData.value.is_active !== props.credential?.is_active) {
        updateData.is_active = formData.value.is_active
      }

      emit('submit', updateData)
    } else {
      // Create payload with all required fields
      const createData: TLSCredentialCreate = {
        name: formData.value.name || undefined,
        ca_cert: formData.value.ca_cert,
        server_cert: formData.value.server_cert,
        server_key: formData.value.server_key,
      }

      emit('submit', createData)
    }

    resetForm()
  } catch (err) {
    logger.error('Error submitting TLS credential:', err)
  } finally {
    isSubmitting.value = false
  }
}
</script>
