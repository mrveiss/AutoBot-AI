// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * MovedToUserApp - where a screen went when it left this console (#20644).
 *
 * Batch Processing and Vision are user work, so they moved to the user app (owner decision
 * 2026-11-02). Their old console paths stay, for bookmarks and the Tools tabs, and show this notice
 * with a link to the new place instead of a broken page.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, EmptyState } from '@autobot/ui'
import { getUserAppUrl } from '@/config/ssot-config'

/** The user-app path of each moved screen. */
type MovedScreen = 'batch' | 'vision'
const USER_APP_PATHS: Record<MovedScreen, string> = { batch: '/batch', vision: '/vision' }

const props = defineProps<{ screen: MovedScreen }>()
const { t } = useI18n()

const href = computed(() => `${getUserAppUrl()}${USER_APP_PATHS[props.screen]}`)
const name = computed(() => t(`tools.moved.${props.screen}`))
</script>

<template>
  <div class="p-6">
    <EmptyState :title="t('tools.moved.title', { name })" :description="t('tools.moved.description', { name })">
      <template #actions>
        <BaseButton as="a" :href="href" target="_blank" rel="noopener">
          {{ t('tools.moved.open', { name }) }}
        </BaseButton>
      </template>
    </EmptyState>
  </div>
</template>
