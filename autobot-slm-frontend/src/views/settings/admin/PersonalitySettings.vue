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

import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import slmApiClient from '@/utils/ApiClient'
import {
  usePersonality,
  TONE_OPTIONS,
  type PersonalityProfile,
  type ProfileCreate,
} from '@/composables/usePersonality'
import { BaseAlert, BaseModal } from '@autobot/ui'

const { t } = useI18n()
const {
  profiles,
  enabled,
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

// ---- voice list for personality voice assignment (#1135) ----
const voiceList = ref<{ id: string; name: string; builtin: boolean }[]>([])

type VoiceEntry = { id: string; name: string; builtin: boolean }

async function fetchVoices() {
  try {
    // Migrated onto slmApiClient (#12420 Phase 2): the client resolves the base
    // URL and injects the SLM bearer token. suppressErrorLog preserves the
    // historic silent-failure behavior (selector shows empty when unavailable).
    const data = await slmApiClient.get<VoiceEntry[] | { voices?: VoiceEntry[] }>(
      '/voice/voices',
      { suppressErrorLog: true }
    )
    voiceList.value = Array.isArray(data) ? data : (data?.voices ?? [])
  } catch {
    // voice list unavailable — selector will show empty
  }
}

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
      voice_id: full.voice_id ?? '',
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
    voice_id: editForm.voice_id as string,
  })
  saving.value = false
  if (result) {
    showSuccess(t('settings.admin.personalitySettings.profileSaved'))
    await fetchProfiles()
  }
}

async function handleActivate() {
  if (!selectedId.value) return
  const ok = await activateProfile(selectedId.value)
  if (ok) showSuccess(t('settings.admin.personalitySettings.profileActivated'))
}

async function handleReset() {
  if (!selectedId.value) return
  const result = await resetProfile(selectedId.value)
  if (result) {
    await selectProfile(selectedId.value)
    showSuccess(t('settings.admin.personalitySettings.profileReset'))
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
    showSuccess(t('settings.admin.personalitySettings.profileDeleted'))
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
    showSuccess(t('settings.admin.personalitySettings.profileCreated', { name }))
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
    voice_id: base.voice_id,
  }
  const result = await createProfile(copy)
  if (result) {
    await fetchProfiles()
    await selectProfile(result.id)
    showSuccess(t('settings.admin.personalitySettings.profileDuplicated', { name: copy.name }))
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
  await Promise.all([fetchProfiles(), fetchActive(), fetchVoices()])
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
    <div class="w-64 shrink-0 border-r border-autobot-border bg-white flex flex-col">
      <!-- Header + toggle -->
      <div class="px-4 py-4 border-b border-autobot-border-subtle">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-autobot-text-primary">{{ $t('settings.admin.personalitySettings.personality') }}</h2>
          <!-- Enable toggle -->
          <button
            type="button"
            :class="[
              'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
              enabled ? 'bg-autobot-primary' : 'bg-autobot-border-strong'
            ]"
            role="switch"
            :aria-checked="enabled"
            :aria-label="$t('settings.admin.personalitySettings.enablePersonality')"
            @click="handleToggle"
          >
            <span
              :class="[
                'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200',
                enabled ? 'translate-x-4' : 'translate-x-0'
              ]"
            />
          </button>
        </div>
        <p class="text-xs text-autobot-text-tertiary">
          {{ enabled ? $t('settings.admin.personalitySettings.activeInjectedIntoSystemPrompt') : $t('settings.admin.personalitySettings.disabledNoPersonalityApplied') }}
        </p>
      </div>

      <!-- Profile list -->
      <ul class="flex-1 overflow-y-auto py-2">
        <li
          v-for="p in profiles"
          :key="p.id"
          :class="[
            'flex items-center gap-2 px-4 py-2.5 cursor-pointer text-sm transition-colors',
            selectedId === p.id ? 'bg-autobot-illus-1-tint text-autobot-text-primary' : 'text-autobot-text-secondary hover:bg-autobot-bg-hover'
          ]"
          @click="selectProfile(p.id)"
        >
          <span class="flex-1 truncate font-medium">{{ p.name }}</span>
          <span
            v-if="p.active"
            class="px-1.5 py-0.5 rounded-sm text-xs bg-autobot-illus-1-tint text-autobot-text-primary font-medium"
          >{{ $t('settings.admin.personalitySettings.active') }}</span>
          <span
            v-if="p.is_system"
            class="px-1.5 py-0.5 rounded-sm text-xs bg-autobot-bg-tertiary text-autobot-text-tertiary"
          >{{ $t('settings.admin.personalitySettings.system') }}</span>
        </li>
      </ul>

      <!-- New / Duplicate buttons -->
      <div class="px-4 py-3 border-t border-autobot-border-subtle flex gap-2">
        <button
          type="button"
          class="flex-1 text-xs px-2 py-1.5 rounded-sm border border-autobot-border-strong text-autobot-text-primary hover:bg-autobot-illus-1-tint transition-colors"
          @click="showNewDialog = true"
        >{{ $t('settings.admin.personalitySettings.new') }}</button>
        <button
          type="button"
          :disabled="!selectedId"
          class="flex-1 text-xs px-2 py-1.5 rounded-sm border border-autobot-border-strong text-autobot-text-secondary hover:bg-autobot-bg-hover disabled:opacity-40 transition-colors"
          @click="handleDuplicate"
        >{{ $t('settings.admin.personalitySettings.duplicate') }}</button>
      </div>
    </div>

    <!-- ================================================================
         RIGHT PANEL — Editor
    ================================================================ -->
    <div class="flex-1 overflow-y-auto bg-autobot-bg-secondary px-6 py-6">

      <!-- Error / success banners -->
      <BaseAlert v-if="error" variant="error" class="mb-4" :message="error" />
      <BaseAlert v-if="successMsg" variant="success" class="mb-4" :message="successMsg" />

      <!-- Empty state -->
      <div v-if="!selectedId" class="flex flex-col items-center justify-center h-64 text-autobot-text-tertiary">
        <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
        <p class="text-sm">{{ $t('settings.admin.personalitySettings.selectAProfileTo') }}</p>
      </div>

      <!-- Editor form -->
      <div v-else>
        <!-- Title row -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h3 class="text-lg font-semibold text-autobot-text-primary">{{ editForm.name }}</h3>
            <p class="text-xs text-autobot-text-tertiary mt-0.5">
              {{ editForm.is_system ? $t('settings.admin.personalitySettings.systemProfile') : `Created by ${editForm.created_by}` }}
            </p>
          </div>
          <!-- Action buttons -->
          <div class="flex items-center gap-2">
            <button
              v-if="!isActive"
              type="button"
              class="text-xs px-3 py-1.5 rounded-sm bg-autobot-primary text-autobot-text-on-primary hover:bg-autobot-primary-hover transition-colors"
              @click="handleActivate"
            >{{ $t('settings.admin.personalitySettings.setActive') }}</button>
            <span
              v-else
              class="text-xs px-3 py-1.5 rounded-sm bg-autobot-illus-1-tint text-autobot-text-primary font-medium"
            >{{ $t('settings.admin.personalitySettings.currentlyActive') }}</span>
            <button
              type="button"
              class="bg-autobot-pill-warn-bg px-2 rounded-sm w-fit text-xs px-3 py-1.5 rounded-sm border border-autobot-warning-light text-autobot-pill-warn-fg hover:bg-autobot-warning-bg transition-colors"
              @click="handleReset"
            >{{ $t('settings.admin.personalitySettings.resetToDefault') }}</button>
            <button
              v-if="!editForm.is_system"
              type="button"
              class="text-xs px-3 py-1.5 rounded-sm border border-autobot-error-light text-autobot-error hover:bg-autobot-error-bg transition-colors"
              @click="confirmDeleteId = selectedId"
            >{{ $t('settings.admin.personalitySettings.delete') }}</button>
          </div>
        </div>

        <div class="space-y-5">

          <!-- Name + Tagline row -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.name') }}</label>
              <input
                v-model="editForm.name"
                type="text"
                class="w-full px-3 py-2 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.tagline') }}</label>
              <input
                v-model="editForm.tagline"
                type="text"
                :placeholder="$t('settings.admin.personalitySettings.oneLineDescription')"
                class="w-full px-3 py-2 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
              />
            </div>
          </div>

          <!-- Tone selector -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.tone') }}</label>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="opt in TONE_OPTIONS"
                :key="opt.value"
                type="button"
                :class="[
                  'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  editForm.tone === opt.value
                    ? 'bg-autobot-primary text-autobot-text-on-primary border-autobot-border-strong'
                    : 'bg-white text-autobot-text-secondary border-autobot-border-strong hover:border-autobot-border-strong'
                ]"
                @click="editForm.tone = opt.value"
              >{{ opt.label }}</button>
            </div>
          </div>

          <!-- Character Traits tag list -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.characterTraits') }}</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="trait in (editForm.character_traits as string[])"
                :key="trait"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-autobot-illus-1-tint text-autobot-text-primary border border-autobot-primary-light"
              >
                {{ trait }}
                <button type="button" class="hover:text-autobot-error" @click="removeTag('character_traits', trait)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="traitInput"
                type="text"
                :placeholder="$t('settings.admin.personalitySettings.addATrait')"
                class="flex-1 px-3 py-1.5 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
                @keydown.enter.prevent="addTrait"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded-sm border border-autobot-border-strong text-autobot-text-secondary hover:bg-autobot-bg-hover"
                @click="addTrait"
              >{{ $t('settings.admin.personalitySettings.add') }}</button>
            </div>
          </div>

          <!-- Operating Style tag list -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.operatingStyle') }}</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="s in (editForm.operating_style as string[])"
                :key="s"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-autobot-illus-2-tint text-autobot-text-primary border border-autobot-border-strong"
              >
                {{ s }}
                <button type="button" class="hover:text-autobot-error" @click="removeTag('operating_style', s)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="styleInput"
                type="text"
                :placeholder="$t('settings.admin.personalitySettings.addAStyleGuideline')"
                class="flex-1 px-3 py-1.5 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
                @keydown.enter.prevent="addStyle"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded-sm border border-autobot-border-strong text-autobot-text-secondary hover:bg-autobot-bg-hover"
                @click="addStyle"
              >{{ $t('settings.admin.personalitySettings.add') }}</button>
            </div>
          </div>

          <!-- Off Limits tag list -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.offLimits') }}</label>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="o in (editForm.off_limits as string[])"
                :key="o"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-autobot-pill-bad-bg text-autobot-pill-bad-fg border border-autobot-error-light"
              >
                {{ o }}
                <button type="button" class="hover:bg-autobot-pill-bad-bg hover:text-autobot-pill-bad-fg" @click="removeTag('off_limits', o)">×</button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="limitInput"
                type="text"
                :placeholder="$t('settings.admin.personalitySettings.addAHardLimit')"
                class="flex-1 px-3 py-1.5 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
                @keydown.enter.prevent="addLimit"
              />
              <button
                type="button"
                class="px-3 py-1.5 text-xs rounded-sm border border-autobot-border-strong text-autobot-text-secondary hover:bg-autobot-bg-hover"
                @click="addLimit"
              >{{ $t('settings.admin.personalitySettings.add') }}</button>
            </div>
          </div>

          <!-- Custom Notes -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.customNotes') }}</label>
            <textarea
              v-model="editForm.custom_notes"
              rows="4"
              :placeholder="$t('settings.admin.personalitySettings.anyAdditionalFreeformInstructions')"
              class="w-full px-3 py-2 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary resize-none"
            />
          </div>

          <!-- Voice Assignment (#1135) -->
          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.personalitySettings.voice') }}</label>
            <select
              v-model="editForm.voice_id"
              class="w-full px-3 py-2 text-sm border border-autobot-border rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-autobot-primary"
            >
              <option value="">{{ $t('settings.admin.personalitySettings.noneUseUserS') }}</option>
              <option
                v-for="v in voiceList"
                :key="v.id"
                :value="v.id"
              >{{ v.name }}{{ v.builtin ? $t('settings.admin.personalitySettings.builtIn') : '' }}</option>
            </select>
            <p class="mt-1 text-xs text-autobot-text-tertiary">
              {{ $t('settings.admin.personalitySettings.whenThisPersonalityIs') }}
            </p>
          </div>

          <!-- Save button -->
          <div class="flex justify-end pt-2">
            <button
              type="button"
              :disabled="saving"
              class="px-5 py-2 rounded-md bg-autobot-primary text-autobot-text-on-primary text-sm font-medium hover:bg-autobot-primary-hover disabled:opacity-50 transition-colors"
              @click="handleSave"
            >
              {{ saving ? $t('settings.admin.personalitySettings.saving') : $t('settings.admin.personalitySettings.saveChanges') }}
            </button>
          </div>

        </div>
      </div>
    </div>

    <!-- ================================================================
         New Profile Dialog
    ================================================================ -->
    <BaseModal
      :close-on-esc="!saving"
      v-model="showNewDialog"
      :title="$t('settings.admin.personalitySettings.newPersonalityProfile')"
      size="sm"
      width="20rem"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <input
        v-model="newName"
        type="text"
        :placeholder="$t('settings.admin.personalitySettings.profileName')"
        autofocus
        class="w-full px-3 py-2 text-sm border border-autobot-border rounded-md focus:outline-hidden focus:ring-2 focus:ring-autobot-primary mb-4"
        @keydown.enter="handleNewProfile"
      />
      <template #actions>
        <button
          type="button"
          class="px-3 py-1.5 text-sm text-autobot-text-secondary hover:bg-autobot-bg-hover rounded-sm border border-autobot-border"
          @click="showNewDialog = false"
        >{{ $t('settings.admin.personalitySettings.cancel') }}</button>
        <button
          type="button"
          :disabled="!newName.trim()"
          class="px-4 py-1.5 text-sm rounded-sm bg-autobot-primary text-autobot-text-on-primary hover:bg-autobot-primary-hover disabled:opacity-40"
          @click="handleNewProfile"
        >{{ $t('settings.admin.personalitySettings.create') }}</button>
      </template>
    </BaseModal>

    <!-- ================================================================
         Delete Confirm Dialog
    ================================================================ -->
    <BaseModal
      :model-value="!!confirmDeleteId"
      :title="$t('settings.admin.personalitySettings.deleteProfile')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
      @close="confirmDeleteId = null"
    >
      <p class="text-sm text-autobot-text-secondary mb-4">
        {{ $t('settings.admin.personalitySettings.thisActionCannotBe') }}
      </p>
      <template #actions>
        <button
          type="button"
          class="px-3 py-1.5 text-sm text-autobot-text-secondary hover:bg-autobot-bg-hover rounded-sm border border-autobot-border"
          @click="confirmDeleteId = null"
        >{{ $t('settings.admin.personalitySettings.cancel') }}</button>
        <button
          type="button"
          class="px-4 py-1.5 text-sm rounded-sm bg-autobot-error-solid text-(--text-on-error) hover:bg-(--color-error-solid-hover)"
          @click="handleDelete"
        >{{ $t('settings.admin.personalitySettings.delete') }}</button>
      </template>
    </BaseModal>

  </div>
</template>
