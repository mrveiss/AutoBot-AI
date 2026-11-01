<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ChatApprovalSettings - admin SLM panel for the two chat approval settings (#20465):
 * `chat.relaxed_approval_categories` and `chat.auto_approve_attachment_turns`.
 *
 * Reads and writes them through the generic SLM settings API (`useSlmJsonSetting`); the
 * write routes are admin-only and each change leaves an audit row server-side.
 */

import { BaseAlert, BaseButton, BaseSwitch } from '@autobot/ui'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSlmJsonSetting } from '@/composables/useSlmJsonSetting'
import {
  APPROVAL_CATEGORIES,
  AUTO_APPROVE_ATTACHMENT_KEY,
  RELAXED_CATEGORIES_KEY,
  parseAutoApprove,
  parseRelaxedCategories,
  type ApprovalCategory,
} from './chatApprovalSettings'

const { t } = useI18n()

const relaxedSetting = useSlmJsonSetting<unknown>(RELAXED_CATEGORIES_KEY)
const autoSetting = useSlmJsonSetting<unknown>(AUTO_APPROVE_ATTACHMENT_KEY)

const relaxed = ref<ApprovalCategory[]>([])
const autoApprove = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  error.value = null
  try {
    relaxed.value = parseRelaxedCategories(await relaxedSetting.load())
    autoApprove.value = parseAutoApprove(await autoSetting.load())
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.chatApprovalSettings.failedToLoad')
  }
}

function isRelaxed(category: ApprovalCategory): boolean {
  return relaxed.value.includes(category)
}

function setRelaxed(category: ApprovalCategory, on: boolean): void {
  const rest = relaxed.value.filter((c) => c !== category)
  relaxed.value = on ? APPROVAL_CATEGORIES.filter((c) => c === category || rest.includes(c)) : rest
}

async function persist(run: () => Promise<boolean>): Promise<void> {
  error.value = null
  try {
    if (!(await run())) error.value = t('settings.chatApprovalSettings.failedToSave')
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('settings.chatApprovalSettings.failedToSave')
  }
}

const saveRelaxed = () =>
  persist(() => relaxedSetting.save(relaxed.value, 'Chat approval categories an administrator has relaxed'))

const saveAutoApprove = () =>
  persist(() =>
    autoSetting.save({ enabled: autoApprove.value }, 'Auto-approve tool calls in chats that used an attached file'),
  )

onMounted(load)
</script>

<template>
  <div class="p-6 space-y-6">
    <BaseAlert v-if="error" variant="error" :message="error" />

    <section class="bg-white rounded-lg shadow-xs border border-gray-200 p-6" data-test="relaxed-section">
      <h2 class="text-lg font-semibold text-gray-900 mb-2">{{ $t('settings.chatApprovalSettings.relaxedTitle') }}</h2>
      <p class="text-sm text-gray-500 mb-6">{{ $t('settings.chatApprovalSettings.relaxedHelp') }}</p>

      <BaseAlert
        v-if="relaxedSetting.saved.value"
        variant="success"
        class="mb-4"
        :message="$t('settings.chatApprovalSettings.saved')"
      />

      <ul class="space-y-3">
        <li v-for="category in APPROVAL_CATEGORIES" :key="category" class="flex items-center justify-between">
          <span class="text-sm text-gray-900">{{ category }}</span>
          <BaseSwitch
            :model-value="isRelaxed(category)"
            :label="category"
            :data-test="`relax-${category}`"
            @update:model-value="setRelaxed(category, $event)"
          />
        </li>
      </ul>

      <div class="mt-8 pt-6 border-t border-gray-200 flex justify-end">
        <BaseButton data-test="save-relaxed" :loading="relaxedSetting.saving.value" @click="saveRelaxed">
          {{ $t('settings.chatApprovalSettings.save') }}
        </BaseButton>
      </div>
    </section>

    <section class="bg-white rounded-lg shadow-xs border border-gray-200 p-6" data-test="auto-approve-section">
      <h2 class="text-lg font-semibold text-gray-900 mb-2">{{ $t('settings.chatApprovalSettings.autoApproveTitle') }}</h2>
      <p class="text-sm text-gray-500 mb-4">{{ $t('settings.chatApprovalSettings.autoApproveHelp') }}</p>

      <BaseAlert
        variant="warning"
        class="mb-4"
        data-test="auto-approve-risk"
        :message="$t('settings.chatApprovalSettings.autoApproveRisk')"
      />
      <BaseAlert
        v-if="autoSetting.saved.value"
        variant="success"
        class="mb-4"
        :message="$t('settings.chatApprovalSettings.saved')"
      />

      <div class="flex items-center justify-between">
        <span class="text-sm font-medium text-gray-900">{{ $t('settings.chatApprovalSettings.autoApproveLabel') }}</span>
        <BaseSwitch
          v-model="autoApprove"
          data-test="auto-approve-switch"
          :label="$t('settings.chatApprovalSettings.autoApproveLabel')"
        />
      </div>

      <div class="mt-8 pt-6 border-t border-gray-200 flex justify-end">
        <BaseButton data-test="save-auto-approve" :loading="autoSetting.saving.value" @click="saveAutoApprove">
          {{ $t('settings.chatApprovalSettings.save') }}
        </BaseButton>
      </div>
    </section>
  </div>
</template>
