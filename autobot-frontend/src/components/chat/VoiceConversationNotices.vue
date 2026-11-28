<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceConversationNotices -- the voice UI's two notices (#22349), on the kit `BaseAlert`: the error banner and the
  "Mic access blocked" warning shown when a microphone-dependent mode is selected but the browser blocks
  getUserMedia behind an untrusted certificate (#1059). Presentational; shared by the voice panel and the overlay.
-->
<template>
  <div class="flex flex-col gap-2">
    <BaseAlert v-if="error" variant="error" size="compact" :message="error" data-testid="voice-error" />
    <BaseAlert v-if="showInsecureContext" variant="warning" :title="$t('chat.voice.micBlocked')" data-testid="voice-cert-warning">
      <p>{{ $t('chat.voice.certRequired') }}</p>
      <ol class="flex flex-col gap-1 ps-4 list-decimal">
        <li>{{ $t('chat.voice.certStep1') }}</li>
        <li>
          {{ $t('chat.voice.certStep2Pre') }}
          <code class="px-1 rounded-sm bg-[var(--aui-color-surface-sunken)] font-mono break-all">chrome://flags/#unsafely-treat-insecure-origin-as-secure</code>,
          {{ $t('chat.voice.certStep2Post', { origin }) }}
        </li>
      </ol>
      <p class="mt-1 text-[var(--aui-color-text-muted)]">{{ $t('chat.voice.walkieTalkieFallback') }}</p>
    </BaseAlert>
  </div>
</template>

<script setup lang="ts">
import { BaseAlert } from '@autobot/ui'

defineProps<{ error: string | null; showInsecureContext: boolean; origin: string }>()
</script>
