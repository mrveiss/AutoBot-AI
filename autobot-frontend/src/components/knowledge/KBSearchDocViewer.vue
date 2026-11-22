<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KBSearchDocViewer — the read-only document pane of the search results (#3296, split out of
  KBSearchResultPanel in #18244): the selected hit's title and meta, its full text with the
  query terms marked, and Copy.
-->
<template>
  <div class="doc-viewer" role="complementary" :aria-label="$t('knowledge.searchPanel.viewerLabel')">
    <div v-if="!result" class="viewer-empty">
      <Icon name="hand-paper" aria-hidden="true" />
      <p>{{ $t('knowledge.searchPanel.selectResult') }}</p>
      <p class="viewer-hint">{{ $t('knowledge.searchPanel.keyboardHint') }}</p>
    </div>

    <template v-else>
      <header class="viewer-header">
        <h4 class="viewer-title">{{ title }}</h4>
        <div class="viewer-meta">
          <span v-if="result.document?.category"><Icon name="folder" aria-hidden="true" /> {{ result.document.category }}</span>
          <span v-if="result.document?.type"><Icon name="tag" aria-hidden="true" /> {{ result.document.type }}</span>
          <span v-if="result.document?.updatedAt"><Icon name="clock" aria-hidden="true" /> {{ formatDate(result.document.updatedAt) }}</span>
          <BaseBadge :variant="scoreVariant(result.score)" size="sm">
            {{ $t('knowledge.searchPanel.match', { score: Math.round(result.score * 100) }) }}
          </BaseBadge>
        </div>
      </header>

      <div v-if="loading" class="viewer-loading" role="status">
        <BaseSpinner size="sm" />
        {{ $t('knowledge.searchPanel.loadingDocument') }}
      </div>
      <div v-else class="viewer-body">
        <pre class="viewer-content" v-html="highlightText(content, query)"></pre>
      </div>

      <footer class="viewer-footer">
        <BaseButton variant="outline" size="sm" :disabled="!content" @click="copyContent">
          <Icon name="copy" aria-hidden="true" /> {{ $t('knowledge.searchPanel.copy') }}
        </BaseButton>
        <span v-if="copied" class="copy-success" role="status"><Icon name="check" aria-hidden="true" /> {{ $t('knowledge.searchPanel.copied') }}</span>
      </footer>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseSpinner } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'
import { createDateFormatter, formatManPageTitle } from '@/utils/formatHelpers'
import { highlightText, scoreVariant } from '@/composables/knowledge/searchHighlight'

const COPIED_MS = 2000

const props = defineProps<{
  result: SearchResult | null
  content: string
  query: string
  loading: boolean
}>()

const logger = createLogger('KBSearchDocViewer')
const { t } = useI18n()
const copied = ref(false)
const formatDate = createDateFormatter({ kind: 'date', invalidText: '' })

const title = computed(
  () =>
    formatManPageTitle(props.result?.document?.title, props.result?.document?.metadata?.factType, t) ||
    t('knowledge.searchPanel.untitled'),
)

async function copyContent(): Promise<void> {
  if (!props.content) return
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, COPIED_MS)
  } catch (err) {
    logger.error('Clipboard write failed:', err)
  }
}
</script>

<style scoped>
.doc-viewer {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
  min-block-size: 0;
}

.viewer-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8) var(--spacing-4);
  color: var(--muted);
  text-align: center;
}

.viewer-empty p {
  margin: 0;
}

.viewer-hint {
  font-size: var(--text-xs);
}

.viewer-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-end: var(--bw) solid var(--line);
}

.viewer-title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}

.viewer-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--muted);
}

.viewer-loading {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  color: var(--muted);
}

.viewer-body {
  flex: 1;
  min-block-size: 0;
  overflow: auto;
  padding: var(--spacing-3) var(--spacing-4);
}

.viewer-content {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.viewer-footer {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-start: var(--bw) solid var(--line);
}

.copy-success {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-sm);
  color: var(--ok-fg);
}
</style>

<!-- The mark sits inside v-html content, which a scoped style cannot reach. -->
<style>
.kb-highlight {
  background-color: var(--kbsearch-highlight-bg);
  color: var(--kbsearch-highlight-text);
  border-radius: var(--radius-xs);
  padding: var(--spacing-0) var(--spacing-px);
  font-weight: 600;
}
</style>
