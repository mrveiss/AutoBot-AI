<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceConversationNotices -- the voice UI's two notices (#22349), on the kit `BaseAlert`: the error banner and the
  "Mic access blocked" warning shown when a microphone-dependent mode is selected but the browser blocks
  getUserMedia behind an untrusted certificate (#1059). Presentational; shared by the voice panel and the overlay.
-->
<template>
  <div class="voice-notices flex flex-col gap-2">
    <BaseAlert v-if="error" variant="error" size="compact" :message="error" data-testid="voice-error" />
    <BaseAlert v-if="showInsecureContext" variant="warning" :title="$t('chat.voice.micBlocked')" data-testid="voice-cert-warning">
      <p>{{ $t('chat.voice.certRequired') }}</p>
      <ol class="voice-notices__steps">
        <li>{{ $t('chat.voice.certStep1') }}</li>
        <li>
          {{ $t('chat.voice.certStep2Pre') }}
          <code class="voice-notices__code">chrome://flags/#unsafely-treat-insecure-origin-as-secure</code>,
          {{ $t('chat.voice.certStep2Post', { origin }) }}
        </li>
      </ol>
      <p class="voice-notices__fallback">{{ $t('chat.voice.walkieTalkieFallback') }}</p>
    </BaseAlert>
  </div>
</template>

<script setup lang="ts">
import { BaseAlert } from '@autobot/ui'

defineProps<{ error: string | null; showInsecureContext: boolean; origin: string }>()
</script>

<style scoped>
.voice-notices__steps {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
  padding-inline-start: var(--aui-space-4);
  list-style: decimal;
}
.voice-notices__code {
  padding: 0 var(--aui-space-1);
  border-radius: var(--aui-radius-sm);
  background: var(--aui-color-surface-sunken);
  font-family: var(--aui-font-mono);
  word-break: break-all;
}
.voice-notices__fallback {
  margin-top: var(--aui-space-1);
  color: var(--aui-color-text-muted);
}
</style>
