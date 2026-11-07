<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->

<!--
  Issue #1133: offer to add the finished index to the Knowledge Base.
  Extracted from CodebaseAnalytics.vue, a grandfathered file that may not grow (#20513).
  Indexing needs a source: with none selected the request would index AutoBot's own
  files (the backend's dev root_path mode), so the action is disabled and says why.
  Styles: `.kb-optin-*` in assets/css/components.css (a shared stylesheet, not another component-local block).
-->
<template>
  <div class="kb-optin-banner">
    <div class="kb-optin-content">
      <Icon name="book" />
      <div class="kb-optin-text">
        <strong>{{ $t('analytics.codebase.knowledgeBase.indexingComplete') }}</strong>
        {{ $t('analytics.codebase.knowledgeBase.addDescription') }}
      </div>
      <button
        class="kb-optin-btn"
        :disabled="adding || !hasSource"
        :title="hasSource ? undefined : $t('analytics.codebase.knowledgeBase.needsSource')"
        @click="emit('add')"
      >
        <i :class="adding ? 'fas fa-spinner fa-spin' : 'plus'"></i>
        {{ adding ? $t('analytics.codebase.knowledgeBase.adding') : $t('analytics.codebase.knowledgeBase.addToKnowledgeBase') }}
      </button>
      <button
        class="kb-optin-dismiss"
        :aria-label="$t('analytics.codebase.actions.dismiss')"
        @click="emit('dismiss')"
      >
        <Icon name="times" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
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
