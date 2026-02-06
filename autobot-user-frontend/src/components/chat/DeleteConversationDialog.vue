<template>
  <BaseModal
    :model-value="visible"
    title="Delete Conversation"
    size="medium"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleCancel"
  >
    <template #default>
        <div class="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
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

          <!-- Knowledge Base Facts Section (Issue #547) -->
          <div v-if="kbFacts && kbFacts.length > 0" class="space-y-3">
            <div class="flex items-center gap-2 p-3 bg-purple-50 rounded-lg">
              <i class="fas fa-brain text-purple-600"></i>
              <div class="flex-1">
                <p class="text-sm font-medium text-purple-700">
                  {{ kbFacts.length }} knowledge fact{{ kbFacts.length > 1 ? 's' : '' }} created during this conversation
                </p>
                <p class="text-xs text-purple-600">
                  Select facts to preserve before deletion
                </p>
              </div>
            </div>

            <!-- Facts List with Selection -->
            <div class="space-y-2 max-h-48 overflow-y-auto border border-purple-200 rounded-lg p-2 bg-white">
              <div
                v-for="fact in kbFacts"
                :key="fact.id"
                class="flex items-start gap-2 p-2 rounded hover:bg-purple-50 transition-colors cursor-pointer"
                @click="toggleFactSelection(fact.id)"
              >
                <input
                  type="checkbox"
                  :checked="selectedFactIds.has(fact.id)"
                  class="mt-1 rounded border-purple-300 text-purple-600 focus:ring-purple-500"
                  @click.stop="toggleFactSelection(fact.id)"
                />
                <div class="flex-1 min-w-0">
                  <p class="text-sm text-gray-800 line-clamp-2">{{ fact.content }}</p>
                  <div class="flex items-center gap-2 mt-1">
                    <span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">{{ fact.category }}</span>
                    <span v-if="fact.important" class="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded">
                      <i class="fas fa-star text-xs"></i> Important
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Quick Actions -->
            <div class="flex items-center gap-2 text-xs">
              <button
                @click="selectAllFacts"
                class="px-2 py-1 text-purple-700 hover:bg-purple-100 rounded transition-colors"
              >
                Select All
              </button>
              <span class="text-gray-300">|</span>
              <button
                @click="deselectAllFacts"
                class="px-2 py-1 text-gray-600 hover:bg-gray-100 rounded transition-colors"
              >
                Deselect All
              </button>
              <span class="flex-1"></span>
              <span class="text-gray-500">
                {{ selectedFactIds.size }} selected for preservation
              </span>
            </div>
          </div>

          <!-- No KB Facts Message -->
          <div v-else-if="kbFactsLoading" class="p-3 bg-purple-50 rounded-lg">
            <p class="text-sm text-purple-600">
              <i class="fas fa-spinner fa-spin mr-2"></i>
              Loading knowledge base facts...
            </p>
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
              <li v-if="kbFacts && kbFacts.length > 0">
                <i class="fas fa-check text-green-600 mr-2"></i>
                {{ getKBFactsSummary() }}
              </li>
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
import { ref, computed, watch } from 'vue'
import type { FileStats } from '@/composables/useConversationFiles'
import type { SessionFact } from '@/models/repositories/ChatRepository'
import { formatFileSize } from '@/utils/formatHelpers'
import BaseModal from '@/components/ui/BaseModal.vue'

const props = defineProps<{
  visible: boolean
  sessionId: string
  sessionName?: string
  fileStats?: FileStats | null
  kbFacts?: SessionFact[] | null
  kbFactsLoading?: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  confirm: [fileAction: string, fileOptions: any, selectedFactIds: string[]]
  cancel: []
}>()

// Local state
const fileAction = ref<'delete' | 'transfer_kb' | 'transfer_shared'>('delete')
const kbCategories = ref('')
const extractText = ref(true)
const sharedPath = ref('')
const isDeleting = ref(false)
const selectedFactIds = ref<Set<string>>(new Set())

// Computed
const hasFiles = computed(() => props.fileStats && props.fileStats.total_files > 0)

// Watch for facts changes to reset selection
watch(() => props.kbFacts, (newFacts) => {
  selectedFactIds.value = new Set()
  // Auto-select facts already marked as important
  if (newFacts) {
    newFacts.forEach(fact => {
      if (fact.important || fact.preserve) {
        selectedFactIds.value.add(fact.id)
      }
    })
  }
}, { immediate: true })

// KB Facts selection methods
const toggleFactSelection = (factId: string) => {
  const newSet = new Set(selectedFactIds.value)
  if (newSet.has(factId)) {
    newSet.delete(factId)
  } else {
    newSet.add(factId)
  }
  selectedFactIds.value = newSet
}

const selectAllFacts = () => {
  if (props.kbFacts) {
    selectedFactIds.value = new Set(props.kbFacts.map(f => f.id))
  }
}

const deselectAllFacts = () => {
  selectedFactIds.value = new Set()
}

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const getKBFactsSummary = (): string => {
  const totalFacts = props.kbFacts?.length || 0
  const preserveCount = selectedFactIds.value.size
  const deleteCount = totalFacts - preserveCount

  if (preserveCount === 0) {
    return `Delete all ${totalFacts} knowledge fact${totalFacts > 1 ? 's' : ''}`
  } else if (deleteCount === 0) {
    return `Preserve all ${totalFacts} knowledge fact${totalFacts > 1 ? 's' : ''}`
  } else {
    return `Delete ${deleteCount} fact${deleteCount > 1 ? 's' : ''}, preserve ${preserveCount} fact${preserveCount > 1 ? 's' : ''}`
  }
}

const getFileActionSummary = (): string => {
  const fileCount = props.fileStats?.total_files || 0
  switch (fileAction.value) {
    case 'delete':
      return `Delete ${fileCount} file${fileCount > 1 ? 's' : ''} permanently`
    case 'transfer_kb':
      return `Transfer ${fileCount} file${fileCount > 1 ? 's' : ''} to Knowledge Base`
    case 'transfer_shared':
      return `Transfer ${fileCount} file${fileCount > 1 ? 's' : ''} to Shared Storage`
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
  // Issue #547: Pass selected fact IDs for preservation
  emit('confirm', fileAction.value, fileOptions, Array.from(selectedFactIds.value))

  // Reset state
  setTimeout(() => {
    isDeleting.value = false
    fileAction.value = 'delete'
    kbCategories.value = ''
    extractText.value = true
    sharedPath.value = ''
    selectedFactIds.value = new Set()
  }, 500)
}

const handleCancel = () => {
  if (isDeleting.value) return

  // Reset state
  fileAction.value = 'delete'
  kbCategories.value = ''
  extractText.value = true
  sharedPath.value = ''
  selectedFactIds.value = new Set()

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
