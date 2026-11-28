<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SkipLink — the SLM console's binding of the shared kit's SkipLink.
 *
 * Issue #754 introduced it here; #17565 promoted the implementation into
 * @autobot/ui so both consoles share one. This wrapper only supplies the
 * console's translated label, which the kit never hardcodes.
 */
import { SkipLink } from '@autobot/ui'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  /** CSS selector of the element that receives focus. */
  target?: string
  /** Translated label for a non-default target; defaults to "skip to main content". */
  label?: string
}>(), {
  target: '#main-content',
  label: undefined,
})

const { t } = useI18n()
</script>

<template>
  <SkipLink :target="props.target" :label="props.label ?? t('common.skipLink.mainContent')" />
</template>
