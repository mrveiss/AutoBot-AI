<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="repos-tab">
    <div class="flex justify-end mb-4">
      <button
        class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm
               text-white transition-colors"
        @click="showAddModal = true"
      >
        + Add Repo
      </button>
    </div>

    <div v-if="repos.length === 0" class="text-center py-12 text-gray-400">
      No repositories registered. Add a skill repo to install community skills.
    </div>

    <table v-else class="w-full text-sm text-left">
      <thead>
        <tr class="text-gray-400 border-b border-gray-700">
          <th class="pb-2 pr-4">Name</th>
          <th class="pb-2 pr-4">Type</th>
          <th class="pb-2 pr-4">URL</th>
          <th class="pb-2 pr-4">Skills</th>
          <th class="pb-2 pr-4">Last Sync</th>
          <th class="pb-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="repo in repos"
          :key="repo.id"
          class="border-b border-gray-800 hover:bg-gray-800/50"
        >
          <td class="py-3 pr-4 text-white font-medium">{{ repo.name }}</td>
          <td class="py-3 pr-4">
            <span
              :class="[
                'text-xs px-2 py-0.5 rounded border',
                repoBadgeClass(repo.repo_type),
              ]"
            >
              {{ repo.repo_type }}
            </span>
          </td>
          <td class="py-3 pr-4 text-gray-400 max-w-xs truncate">{{ repo.url }}</td>
          <td class="py-3 pr-4 text-gray-300">{{ repo.skill_count }}</td>
          <td class="py-3 pr-4 text-gray-400">
            {{ repo.last_synced ? new Date(repo.last_synced).toLocaleString() : 'Never' }}
          </td>
          <td class="py-3">
            <button
              class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs
                     text-gray-300 transition-colors"
              @click="$emit('sync', repo.id)"
            >
              Sync
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Add Repo Modal -->
    <div
      v-if="showAddModal"
      class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      @click.self="showAddModal = false"
    >
      <div class="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-md p-6">
        <h3 class="text-lg font-bold text-white mb-4">Add Skill Repository</h3>
        <div class="space-y-3">
          <label class="block">
            <span class="text-sm text-gray-400">Name</span>
            <input
              v-model="newRepo.name"
              type="text"
              placeholder="my-skills"
              class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                     text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </label>
          <label class="block">
            <span class="text-sm text-gray-400">URL</span>
            <input
              v-model="newRepo.url"
              type="text"
              placeholder="https://... or /path/to/dir"
              class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                     text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </label>
          <label class="block">
            <span class="text-sm text-gray-400">Type</span>
            <select
              v-model="newRepo.repo_type"
              class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                     text-white text-sm focus:outline-none focus:border-blue-500"
            >
              <option value="git">Git</option>
              <option value="local">Local</option>
              <option value="http">HTTP</option>
              <option value="mcp">MCP</option>
            </select>
          </label>
        </div>
        <div class="flex gap-3 mt-5">
          <button
            class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm
                   text-white transition-colors"
            @click="submitAdd"
          >
            Add
          </button>
          <button
            class="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm
                   text-gray-300 transition-colors"
            @click="showAddModal = false"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { SkillRepo } from '@/composables/useSkills'

defineProps<{ repos: readonly SkillRepo[] }>()
const emit = defineEmits<{
  sync: [id: string]
  add: [payload: Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>]
}>()

const showAddModal = ref(false)
const newRepo = ref<Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>>({
  name: '',
  url: '',
  repo_type: 'git',
})

function repoBadgeClass(repoType: string): string {
  const map: Record<string, string> = {
    git: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    local: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
    http: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    mcp: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  }
  return map[repoType] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'
}

function submitAdd(): void {
  emit('add', { ...newRepo.value })
  showAddModal.value = false
  newRepo.value = { name: '', url: '', repo_type: 'git' }
}
</script>
