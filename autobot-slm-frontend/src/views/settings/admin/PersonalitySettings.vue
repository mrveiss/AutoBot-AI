<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * PersonalitySettings - Personality Profile Management
 *
 * Left panel: profile list with active/system badges, enable toggle,
 * New and Duplicate buttons.
 * Right panel: structured editor — tone, tag-list fields, custom notes,
 * plus Activate / Reset / Delete actions.
 *
 * Related Issue: #964
 */

import { ref, reactive, watch, onMounted, computed } from 'vue'
import {
  usePersonality,
  TONE_OPTIONS,
  type PersonalityProfile,
  type ProfileCreate,
} from '@/composables/usePersonality'

const {
  profiles,
  activeProfile,
  enabled,
  loading,
  error,
  fetchProfiles,
  fetchProfile,
  fetchActive,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
  resetProfile,
  toggleEnabled,
} = usePersonality()

// ---- local state ----
const selectedId = ref<string | null>(null)
const editForm = reactive<Partial<PersonalityProfile>>({})
const saving = ref(false)
const successMsg = ref<string | null>(null)
const showNewDialog = ref(false)
const newName = ref('')
const confirmDeleteId = ref<string | null>(null)

const selectedProfile = computed(() =>
  profiles.value.find((p) => p.id === selectedId.value) ?? null
)

const isActive = computed(() => selectedId.value === (profiles.value.find((p) => p.active)?.id ?? null))

// ---- tag-list helpers ----
const traitInput = ref('')
const styleInput = ref('')
const limitInput = ref('')

type TagKey = 'character_traits' | 'operating_style' | 'off_limits'

function _pushTag(key: TagKey, value: string): void {
  const val = value.trim()
  if (!val) return
  const list = (editForm[key] ?? []) as string[]
  if (!list.includes(val)) {
    editForm[key] = [...list, val]
  }
}

function addTrait() { _pushTag('character_traits', traitInput.value); traitInput.value = '' }
function addStyle() { _pushTag('operating_style', styleInput.value); styleInput.value = '' }
function addLimit() { _pushTag('off_limits', limitInput.value); limitInput.value = '' }

function removeTag(key: TagKey, tag: string) {
  editForm[key] = ((editForm[key] ?? []) as string[]).filter((t) => t !== tag)
}

// ---- load profile into editor ----
async function selectProfile(id: string) {
  selectedId.value = id
  traitInput.value = ''
  styleInput.value = ''
  limitInput.value = ''
  const full = await fetchProfile(id)
  if (full) {
    Object.assign(editForm, {
      name: full.name,
      tagline: full.tagline,
      tone: full.tone,
      character_traits: [...full.character_traits],
      operating_style: [...full.operating_style],
      off_limits: [...full.off_limits],
      custom_notes: full.custom_notes,
      is_system: full.is_system,
      created_by: full.created_by,
    })
  }
}

// ---- actions ----
async function handleSave() {
  if (!selectedId.value) return
  saving.value = true
  const result = await updateProfile(selectedId.value, {
    name: editForm.name,
    tagline: editForm.tagline,
    tone: editForm.tone as string,
    character_traits: editForm.character_traits as string[],
    operating_style: editForm.operating_style as string[],
    off_limits: editForm.off_limits as string[],
    custom_notes: editForm.custom_notes,
  })
  saving.value = false
  if (result) {
    showSuccess('Profile saved.')
    await fetchProfiles()
  }
}

async function handleActivate() {
  if (!selectedId.value) return
  const ok = await activateProfile(selectedId.value)
  if (ok) showSuccess('Profile activated.')
}

async function handleReset() {
  if (!selectedId.value) return
  const result = await resetProfile(selectedId.value)
  if (result) {
    await selectProfile(selectedId.value)
    showSuccess('Profile reset to default values.')
  }
}

async function handleDelete() {
  if (!confirmDeleteId.value) return
  const id = confirmDeleteId.value
  confirmDeleteId.value = null
  const ok = await deleteProfile(id)
  if (ok) {
    if (selectedId.value === id) {
      selectedId.value = null
      Object.assign(editForm, {})
    }
    showSuccess('Profile deleted.')
  }
}

async function handleNewProfile() {
  const name = newName.value.trim()
  if (!name) return
  showNewDialog.value = false
  newName.value = ''
  const result = await createProfile({ name } as ProfileCreate)
  if (result) {
    await fetchProfiles()
    await selectProfile(result.id)
    showSuccess(`Profile "${name}" created.`)
  }
}

async function handleDuplicate() {
  if (!selectedId.value) return
  const base = await fetchProfile(selectedId.value)
  if (!base) return
  const copy: ProfileCreate = {
    name: `${base.name} (copy)`,
    tagline: base.tagline,
    tone: base.tone,
    character_traits: [...base.character_traits],
    operating_style: [...base.operating_style],
    off_limits: [...base.off_limits],
    custom_notes: base.custom_notes,
  }
  const result = await createProfile(copy)
  if (result) {
    await fetchProfiles()
    await selectProfile(result.id)
    showSuccess(`Duplicated as "${copy.name}".`)
  }
}

async function handleToggle() {
  await toggleEnabled(!enabled.value)
}

function showSuccess(msg: string) {
  successMsg.value = msg
  setTimeout(() => { successMsg.value = null }, 4000)
}

onMounted(async () => {
  await fetchProfiles()
  await fetchActive()
  if (profiles.value.length > 0) {
    await selectProfile(profiles.value[0].id)
  }
})
</script>

<template>
  <div class="flex h-full gap-0 overflow-hidden">

    <!-- ================================================================
         LEFT PANEL — Profile List
    ================================================================ -->
    <div class="w-64 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
      <!-- Header + toggle -->
      <div class="px-4 py-4 border-b border-gray-100">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-gray-800">Personality</h2>
          <!-- Enable toggle -->
          <button
            type="button"
            :class="[
              'relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
              enabled ? 'bg-indigo-600' : 'bg-gray-300'
            ]"
            role="switch"
            :aria-checked="enabled"
            aria-label="Enable personality"
            @click="handleToggle"
          >
            <span
              :class="[
                'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200',
                enabled ? 'translate-x-4' : 'translate-x-0'
              ]"
            />
          </button>
        </div>
        <p class="text-xs text-gray-500">
          {{ enabled ? 'Active — injected into system prompt' : 'Disabled — no personality applied' }}
        </p>
      </div>

      <!-- Profile list -->
      <ul class="flex-1 overflow-y-auto py-2">
        <li
          v-for="p in profiles"
          :key="p.id"
          :class="[
            'flex items-center gap-2 px-4 py-2.5 cursor-pointer text-sm transition-colors',
            selectedId === p.id ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-50'
          ]"
          @click="selectProfile(p.id)"
        >
          <span class="flex-1 truncate font-medium">{{ p.name }}</span>
          <span
            v-if="p.active"
            class="px-1.5 py-0.5 rounded text-xs bg-indigo-100 text-indigo-700 font-medium"
          >Active</span>
          <span
            v-if="p.is_system"
            class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500"
          >System</span>
        </li>
      </ul>

      <!-- New / Duplicate buttons -->
      <div class="px-4 py-3 border-t border-gray-100 flex gap-2">
        <button
          type="button"
          class="flex-1 text-xs px-2 py-1.5 rounded border border-indigo-300 text-indigo-700 hover:bg-indigo-50 transition-colors"
          @click="showNewDialog = true"
        >+ New</button>
        <button
          type="button"
          :disabled="!selectedId"
          class="flex-1 text-xs px-2 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          @click="handleDuplicate"
        >Duplicate</button>
      </div>
    </div>

    <!-- ================================================================
         RIGHT PANEL — Editor
    ================================================================ -->
    <div class="flex-1 overflow-y-auto bg-gray-50 px-6 py-6">

      <!-- Error / success banners -->
      <div v-if="error" class="mb-4 px-4 py-3 rounded bg-red-50 border border-red-200 text-sm text-red-700">
        {{ error }}
      </div>
      <div v-if="successMsg" class="mb-4 px-4 py-3 rounded bg-green-50 border border-green-200 text-sm text-green-700">
        {{ successMsg }}
      </div>

      <!-- Empty state -->
      <div v-if="!selectedId" class="flex flex-col items-center justify-center h-64 text-gray-400">
        <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
        <p class="text-sm">Select a profile to edit</p>
      </div>

      <!-- Editor form -->
      <div v-else>
        <!-- Title row -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">{{ editForm.name }}</h3>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ editForm.is_system ? 'System profile' : `Created by ${editForm.created_by}` }}
            </p>
          </div>
          <!-- Action buttons -->
          <div class="flex items-center gap-2">
            <button
              v-if="!isActive"
              type="button"
              class="text-xs px-3 py-1.5 rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
              @click="handleActivate"
            >Set Active</button>
            <span
              v-else
              class="text-xs px-3 py-1.5 rounded bg-indigo-100 text-indigo-700 font-medium"
            >Currently Active</span>
            <button
              type="button"
              class="text-xs px-3 py-1.5 rounded border border-amber-300 text-amber-700 hover:bg-amber-50 transition-colors"
              @click="handleReset"
            >Reset to Default</button>
            <button
              v-if="!editForm.is_system"
              type="button"
              class="text-xs px-3 py-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
              @click="confirmDeleteId = selectedId"
            >Delete</button>
          </div>
        </div>

        <div class="space-y-5">

          <!-- Name + Tagline row -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Name</label>
              <input
                v-model="editForm.name"
                type="text"
                class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Tagline</label>
              <input
                v-model="editForm.tagline"
                type="text"
                placeholder="One-line description"
                class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
          </div>

          <!-- Tone selector -->
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Tone</label>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="opt in TONE_OPTIONS"
                :key="opt.value"
                type="button"
                :class="[
                  'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  editForm.tone === opt.value
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400'
                ]"
                @click="editForm.tone = opt.value"
              >{{ opt.label }}</button>
            </div>
          </div>

          <!-- Character Traits tag list -->
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Character Traits</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="trait in (editForm.character_traits as string[])"
                :key="trait"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-200"
              >
                {{ trait }}
                <button type="button" class="hover:text-red-500" @click="removeTag('character_traits', trait)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="traitInput"
                type="text"
                placeholder="Add a trait…"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
                @keydown.enter.prevent="addTrait"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                @click="addTrait"
              >Add</button>
            </div>
          </div>

          <!-- Operating Style tag list -->
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Operating Style</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="s in (editForm.operating_style as string[])"
                :key="s"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-50 text-purple-700 border border-purple-200"
              >
                {{ s }}
                <button type="button" class="hover:text-red-500" @click="removeTag('operating_style', s)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="styleInput"
                type="text"
                placeholder="Add a style guideline…"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
                @keydown.enter.prevent="addStyle"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                @click="addStyle"
              >Add</button>
            </div>
          </div>

          <!-- Off Limits tag list -->
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Off Limits</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="o in (editForm.off_limits as string[])"
                :key="o"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-red-50 text-red-700 border border-red-200"
              >
                {{ o }}
                <button type="button" class="hover:text-red-700" @click="removeTag('off_limits', o)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="limitInput"
                type="text"
                placeholder="Add a hard limit…"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
                @keydown.enter.prevent="addLimit"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                @click="addLimit"
              >Add</button>
            </div>
          </div>

          <!-- Custom Notes -->
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Custom Notes</label>
            <textarea
              v-model="editForm.custom_notes"
              rows="4"
              placeholder="Any additional freeform instructions…"
              class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
            />
          </div>

          <!-- Save button -->
          <div class="flex justify-end pt-2">
            <button
              type="button"
              :disabled="saving"
              class="px-5 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              @click="handleSave"
            >
              {{ saving ? 'Saving…' : 'Save Changes' }}
            </button>
          </div>

        </div>
      </div>
    </div>

    <!-- ================================================================
         New Profile Dialog
    ================================================================ -->
    <Teleport to="body">
      <div
        v-if="showNewDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showNewDialog = false"
      >
        <div class="bg-white rounded-xl shadow-xl p-6 w-80">
          <h3 class="text-sm font-semibold text-gray-800 mb-3">New Personality Profile</h3>
          <input
            v-model="newName"
            type="text"
            placeholder="Profile name"
            autofocus
            class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-400 mb-4"
            @keydown.enter="handleNewProfile"
          />
          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 rounded border border-gray-200"
              @click="showNewDialog = false"
            >Cancel</button>
            <button
              type="button"
              :disabled="!newName.trim()"
              class="px-4 py-1.5 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40"
              @click="handleNewProfile"
            >Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ================================================================
         Delete Confirm Dialog
    ================================================================ -->
    <Teleport to="body">
      <div
        v-if="confirmDeleteId"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="confirmDeleteId = null"
      >
        <div class="bg-white rounded-xl shadow-xl p-6 w-80">
          <h3 class="text-sm font-semibold text-gray-800 mb-2">Delete Profile</h3>
          <p class="text-sm text-gray-600 mb-4">
            This action cannot be undone. The profile will be permanently removed.
          </p>
          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 rounded border border-gray-200"
              @click="confirmDeleteId = null"
            >Cancel</button>
            <button
              type="button"
              class="px-4 py-1.5 text-sm rounded bg-red-600 text-white hover:bg-red-700"
              @click="handleDelete"
            >Delete</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>
