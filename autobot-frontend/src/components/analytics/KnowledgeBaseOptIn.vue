<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->

<!--
  Issue #1133: offer to add the finished index to the Knowledge Base.
  Extracted from CodebaseAnalytics.vue, a grandfathered file that may not grow (#20513).
  Indexing needs a source: with none selected the request would index AutoBot's own
  files (the backend's dev root_path mode), so the action is disabled and says why.
  Styles: `.kb-optin-banner/-content/-text` in assets/css/components.css; the buttons are the kit's BaseButton.
-->
<template>
  <div class="kb-optin-banner">
    <div class="kb-optin-content">
      <Icon name="book" />
      <div class="kb-optin-text">
        <strong>{{ $t('analytics.codebase.knowledgeBase.indexingComplete') }}</strong>
        {{ $t('analytics.codebase.knowledgeBase.addDescription') }}
      </div>
      <BaseButton
        variant="success"
        size="sm"
        :loading="adding"
        :disabled="!hasSource"
        :title="hasSource ? undefined : $t('analytics.codebase.knowledgeBase.needsSource')"
        @click="emit('add')"
      >
        <template #icon-left><Icon name="plus" /></template>
        {{ adding ? $t('analytics.codebase.knowledgeBase.adding') : $t('analytics.codebase.knowledgeBase.addToKnowledgeBase') }}
      </BaseButton>
      <BaseButton
        variant="ghost"
        size="sm"
        :aria-label="$t('analytics.codebase.actions.dismiss')"
        @click="emit('dismiss')"
      >
        <Icon name="times" />
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

defineProps<{
  /** An add request is in flight. */
  adding: boolean
  /** A code source is selected; without one the action is disabled. */
  hasSource: boolean
}>()

const emit = defineEmits<{
  add: []
  dismiss: []
}>()
</script>
