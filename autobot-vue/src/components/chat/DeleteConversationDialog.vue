<template>
  <BaseModal
    :model-value="visible"
    title="Delete Conversation"
    size="small"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleCancel"
  >
    <template #default>
        <div class="p-4 space-y-4">
          <!-- Warning Message -->
          <div class="flex items-start gap-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <i class="fas fa-exclamation-triangle text-yellow-600 mt-0.5"></i>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-yellow-800 font-medium">
                This action cannot be undone
              </p>
              <p class="text-xs text-yellow-700 mt-1">
                The conversation and all messages will be permanently deleted.
              </p>
            </div>
          </div>

          <!-- File Information -->
          <div v-if="fileStats && fileStats.total_files > 0" class="space-y-3">
            <div class="flex items-center gap-2 p-3 bg-blueGray-50 rounded-lg">
              <i class="fas fa-paperclip text-blueGray-600"></i>
              <div class="flex-1">
                <p class="text-sm font-medium text-blueGray-700">
                  {{ fileStats.total_files }} attached file{{ fileStats.total_files > 1 ? 's' : '' }}
                </p>
                <p class="text-xs text-blueGray-600">
                  Total size: {{ formatFileSize(fileStats.total_size_bytes) }}
                </p>
              </div>
            </div>

            <!-- File Action Options -->
            <div class="space-y-2">
              <p class="text-sm font-medium text-gray-700">What should we do with the attached files?</p>

              <label class="flex items-start p-3 border rounded-lg cursor-pointer transition-colors"
                     :class="fileAction === 'delete' ? 'border-red-500 bg-red-50' : 'border-gray-300 hover:border-gray-400'">
                <input
                  type="radio"
                  v-model="fileAction"
                  value="delete"
                  class="mt-0.5 mr-3"
                />
                <div class="flex-1">
                  <div class="flex items-center gap-2">
                    <i class="fas fa-trash text-red-600"></i>
                    <span class="text-sm font-medium text-gray-900">Delete files</span>
                  </div>
                  <p class="text-xs text-gray-600 mt-1">
                    Permanently delete all attached files
                  </p>
                </div>
              </label>

              <label class="flex items-start p-3 border rounded-lg cursor-pointer transition-colors"
                     :class="fileAction === 'transfer_kb' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'">
                <input
                  type="radio"
                  v-model="fileAction"
                  value="transfer_kb"
                  class="mt-0.5 mr-3"
                />
                <div class="flex-1">
                  <div class="flex items-center gap-2">
                    <i class="fas fa-book text-indigo-600"></i>
                    <span class="text-sm font-medium text-gray-900">Transfer to Knowledge Base</span>
                  </div>
                  <p class="text-xs text-gray-600 mt-1">
                    Move files to knowledge base for future use
                  </p>
                </div>
              </label>

              <label class="flex items-start p-3 border rounded-lg cursor-pointer transition-colors"
                     :class="fileAction === 'transfer_shared' ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-gray-400'">
                <input
                  type="radio"
                  v-model="fileAction"
                  value="transfer_shared"
                  class="mt-0.5 mr-3"
                />
                <div class="flex-1">
                  <div class="flex items-center gap-2">
                    <i class="fas fa-share-alt text-green-600"></i>
                    <span class="text-sm font-medium text-gray-900">Transfer to Shared Storage</span>
                  </div>
                  <p class="text-xs text-gray-600 mt-1">
                    Move files to shared storage for team access
                  </p>
                </div>
              </label>
            </div>

            <!-- Transfer Options (shown when KB transfer selected) -->
            <div v-if="fileAction === 'transfer_kb'" class="space-y-3 p-3 bg-indigo-50 rounded-lg border border-indigo-200">
              <p class="text-sm font-medium text-indigo-900">Knowledge Base Options</p>

              <div>
                <label class="block text-xs font-medium text-indigo-700 mb-1">
                  Categories (comma-separated)
                </label>
                <input
                  v-model="kbCategories"
                  type="text"
                  class="w-full px-3 py-2 text-sm border border-indigo-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g., research, documentation"
                />
              </div>

              <label class="flex items-center gap-2">
                <input
                  type="checkbox"
                  v-model="extractText"
                  class="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span class="text-xs text-indigo-700">Extract text content from documents</span>
              </label>
            </div>

            <!-- Transfer Options (shown when shared transfer selected) -->
            <div v-if="fileAction === 'transfer_shared'" class="space-y-3 p-3 bg-green-50 rounded-lg border border-green-200">
              <p class="text-sm font-medium text-green-900">Shared Storage Options</p>

              <div>
                <label class="block text-xs font-medium text-green-700 mb-1">
                  Target Folder Path
                </label>
                <input
                  v-model="sharedPath"
                  type="text"
                  class="w-full px-3 py-2 text-sm border border-green-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="e.g., archive/2025/"
                />
              </div>
            </div>
          </div>

          <!-- No Files Message -->
          <div v-else class="p-3 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-600">
              <i class="fas fa-info-circle mr-2"></i>
              This conversation has no attached files.
            </p>
          </div>

          <!-- Confirmation Summary -->
          <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <p class="text-sm font-medium text-gray-900 mb-2">Action Summary:</p>
            <ul class="text-xs text-gray-700 space-y-1">
              <li><i class="fas fa-check text-green-600 mr-2"></i>Delete conversation and all messages</li>
              <li v-if="fileStats && fileStats.total_files > 0">
                <i class="fas fa-check text-green-600 mr-2"></i>
                {{ getFileActionSummary() }}
              </li>
            </ul>
          </div>
        </div>
    </template>

    <template #actions>
      <button
        @click="handleCancel"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
        :disabled="isDeleting"
      >
        Cancel
      </button>
      <button
        @click="handleConfirm"
        class="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 flex items-center gap-2"
        :disabled="isDeleting"
      >
        <i v-if="isDeleting" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-trash"></i>
        {{ isDeleting ? 'Deleting...' : 'Delete Conversation' }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FileStats } from '@/composables/useConversationFiles'
import { formatFileSize } from '@/utils/formatHelpers'
import BaseModal from '@/components/ui/BaseModal.vue'

const props = defineProps<{
  visible: boolean
  sessionId: string
  sessionName?: string
  fileStats?: FileStats | null
}>()

const emit = defineEmits<{
  confirm: [fileAction: string, fileOptions: any]
  cancel: []
}>()

// Local state
const fileAction = ref<'delete' | 'transfer_kb' | 'transfer_shared'>('delete')
const kbCategories = ref('')
const extractText = ref(true)
const sharedPath = ref('')
const isDeleting = ref(false)

// Computed
const hasFiles = computed(() => props.fileStats && props.fileStats.total_files > 0)

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const getFileActionSummary = (): string => {
  switch (fileAction.value) {
    case 'delete':
      return `Delete ${props.fileStats?.total_files} file${props.fileStats?.total_files > 1 ? 's' : ''} permanently`
    case 'transfer_kb':
      return `Transfer ${props.fileStats?.total_files} file${props.fileStats?.total_files > 1 ? 's' : ''} to Knowledge Base`
    case 'transfer_shared':
      return `Transfer ${props.fileStats?.total_files} file${props.fileStats?.total_files > 1 ? 's' : ''} to Shared Storage`
    default:
      return 'No file action'
  }
}

const buildFileOptions = (): any => {
  if (fileAction.value === 'transfer_kb') {
    return {
      categories: kbCategories.value.split(',').map(c => c.trim()).filter(c => c),
      extract_text: extractText.value
    }
  } else if (fileAction.value === 'transfer_shared') {
    return {
      target_path: sharedPath.value.trim() || 'archive/'
    }
  }

  return null
}

const handleConfirm = () => {
  isDeleting.value = true

  const fileOptions = buildFileOptions()
  emit('confirm', fileAction.value, fileOptions)

  // Reset state
  setTimeout(() => {
    isDeleting.value = false
    fileAction.value = 'delete'
    kbCategories.value = ''
    extractText.value = true
    sharedPath.value = ''
  }, 500)
}

const handleCancel = () => {
  if (isDeleting.value) return

  // Reset state
  fileAction.value = 'delete'
  kbCategories.value = ''
  extractText.value = true
  sharedPath.value = ''

  emit('cancel')
}
</script>

<style scoped>
/* Custom radio button styling */
input[type="radio"] {
  @apply w-4 h-4 cursor-pointer;
}

input[type="radio"]:checked {
  @apply accent-indigo-600;
}
</style>
