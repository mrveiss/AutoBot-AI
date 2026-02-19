// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * PromptsSettings - Prompt Template Management
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides management of system prompts for LLM interactions.
 */

import { ref, computed, onMounted } from 'vue'
import { useAutobotApi, type PromptTemplate } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Prompts data
const prompts = ref<PromptTemplate[]>([])
const selectedPrompt = ref<PromptTemplate | null>(null)
const editedContent = ref('')
const searchQuery = ref('')

// Category filter
const selectedCategory = ref<string | null>(null)

// Computed
const categories = computed(() => {
  const cats = new Set(prompts.value.map(p => p.category))
  return Array.from(cats).sort()
})

const filteredPrompts = computed(() => {
  let filtered = prompts.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.content.toLowerCase().includes(query)
    )
  }

  if (selectedCategory.value) {
    filtered = filtered.filter(p => p.category === selectedCategory.value)
  }

  return filtered
})

const hasUnsavedChanges = computed(() => {
  if (!selectedPrompt.value) return false
  return editedContent.value !== selectedPrompt.value.content
})

// Methods
async function loadPrompts(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    prompts.value = await api.getPromptTemplates()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load prompts'
  } finally {
    loading.value = false
  }
}

function selectPrompt(prompt: PromptTemplate): void {
  if (hasUnsavedChanges.value) {
    if (!confirm('You have unsaved changes. Discard them?')) {
      return
    }
  }
  selectedPrompt.value = prompt
  editedContent.value = prompt.content
}

function clearSelection(): void {
  selectedPrompt.value = null
  editedContent.value = ''
}

async function savePrompt(): Promise<void> {
  if (!selectedPrompt.value) return

  saving.value = true
  error.value = null

  try {
    await api.updatePromptTemplate(selectedPrompt.value.id, {
      content: editedContent.value,
    })

    // Update local data
    const index = prompts.value.findIndex(p => p.id === selectedPrompt.value?.id)
    if (index !== -1) {
      prompts.value[index] = {
        ...prompts.value[index],
        content: editedContent.value,
        modified_at: new Date().toISOString(),
      }
    }

    selectedPrompt.value.content = editedContent.value

    success.value = 'Prompt saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save prompt'
  } finally {
    saving.value = false
  }
}

async function revertToDefault(): Promise<void> {
  if (!selectedPrompt.value) return

  if (!confirm('Are you sure you want to revert this prompt to its default content?')) {
    return
  }

  saving.value = true
  error.value = null

  try {
    await api.revertPromptToDefault(selectedPrompt.value.id)
    success.value = 'Prompt reverted to default'

    // Reload prompts to get the default content
    await loadPrompts()

    // Re-select the prompt if it still exists
    const prompt = prompts.value.find(p => p.id === selectedPrompt.value?.id)
    if (prompt) {
      selectedPrompt.value = prompt
      editedContent.value = prompt.content
    } else {
      clearSelection()
    }

    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to revert prompt'
  } finally {
    saving.value = false
  }
}

// Initialize
onMounted(() => {
  loadPrompts()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button @click="error = null" class="ml-auto text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Header with Controls -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">Prompt Templates</h2>
        <button
          @click="loadPrompts"
          :disabled="loading"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="loading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Reload Prompts
        </button>
      </div>

      <!-- Filters -->
      <div class="flex flex-col sm:flex-row gap-4">
        <div class="flex-1">
          <div class="relative">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search prompts..."
              class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>
        <div class="sm:w-48">
          <select
            v-model="selectedCategory"
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option :value="null">All Categories</option>
            <option v-for="cat in categories" :key="cat" :value="cat">
              {{ cat }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <div class="grid lg:grid-cols-2 gap-6">
      <!-- Prompts List -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="p-4 bg-gray-50 border-b border-gray-200">
          <h3 class="font-medium text-gray-900">Available Prompts ({{ filteredPrompts.length }})</h3>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-12">
          <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>

        <!-- Empty State -->
        <div v-else-if="filteredPrompts.length === 0" class="p-8 text-center">
          <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p class="text-gray-500">
            {{ prompts.length === 0 ? 'No prompts available' : 'No prompts match your search' }}
          </p>
        </div>

        <!-- Prompts -->
        <div v-else class="divide-y divide-gray-100 max-h-[500px] overflow-y-auto">
          <button
            v-for="prompt in filteredPrompts"
            :key="prompt.id"
            @click="selectPrompt(prompt)"
            :class="[
              'w-full text-left p-4 hover:bg-gray-50 transition-colors',
              selectedPrompt?.id === prompt.id ? 'bg-primary-50 border-l-4 border-primary-500' : '',
            ]"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <h4 class="font-medium text-gray-900 truncate">{{ prompt.name }}</h4>
                <p class="text-sm text-gray-500 mt-1 line-clamp-2">
                  {{ prompt.content.substring(0, 100) }}{{ prompt.content.length > 100 ? '...' : '' }}
                </p>
                <div class="flex items-center gap-2 mt-2">
                  <span class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                    {{ prompt.category }}
                  </span>
                  <span v-if="prompt.is_default" class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
                    Default
                  </span>
                </div>
              </div>
              <svg class="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>
        </div>
      </div>

      <!-- Prompt Editor -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="p-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
          <h3 class="font-medium text-gray-900">
            {{ selectedPrompt ? `Editing: ${selectedPrompt.name}` : 'Select a Prompt' }}
          </h3>
          <div v-if="hasUnsavedChanges" class="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs font-medium">
            Unsaved Changes
          </div>
        </div>

        <div v-if="!selectedPrompt" class="p-8 text-center">
          <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          <p class="text-gray-500">Select a prompt from the list to edit</p>
        </div>

        <div v-else class="p-4">
          <!-- Prompt Info -->
          <div class="mb-4 p-3 bg-gray-50 rounded-lg">
            <div class="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span class="text-gray-500">Category:</span>
                <span class="ml-2 font-medium text-gray-900">{{ selectedPrompt.category }}</span>
              </div>
              <div>
                <span class="text-gray-500">Status:</span>
                <span :class="[
                  'ml-2 font-medium',
                  selectedPrompt.is_default ? 'text-blue-600' : 'text-gray-900',
                ]">
                  {{ selectedPrompt.is_default ? 'Default' : 'Custom' }}
                </span>
              </div>
              <div class="col-span-2">
                <span class="text-gray-500">Last Modified:</span>
                <span class="ml-2 font-medium text-gray-900">
                  {{ selectedPrompt.modified_at ? new Date(selectedPrompt.modified_at).toLocaleString() : 'Never' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Editor -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">Prompt Content</label>
            <textarea
              v-model="editedContent"
              rows="12"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm resize-y"
              placeholder="Enter prompt content..."
            ></textarea>
          </div>

          <!-- Actions -->
          <div class="flex flex-wrap gap-3">
            <button
              @click="savePrompt"
              :disabled="saving || !hasUnsavedChanges"
              class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center gap-2"
            >
              <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
              Save Changes
            </button>

            <button
              @click="revertToDefault"
              :disabled="saving || selectedPrompt.is_default"
              class="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              Revert to Default
            </button>

            <button
              @click="clearSelection"
              class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
