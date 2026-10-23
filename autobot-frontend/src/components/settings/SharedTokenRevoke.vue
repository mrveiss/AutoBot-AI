<template>
  <div class="flex flex-col gap-2 border-t border-autobot-border pt-3" data-testid="shared-token-revoke">
    <h5 class="text-sm font-semibold text-autobot-text-primary">{{ t('settings.providerAuth.shared.heading') }}</h5>
    <p class="text-xs text-autobot-text-muted">{{ t('settings.providerAuth.shared.description') }}</p>
    <div class="flex flex-wrap gap-2">
      <BaseButton
        v-for="p in providers"
        :key="p.name"
        variant="error"
        size="sm"
        :loading="busy"
        :data-testid="`shared-revoke-${p.name}`"
        @click="revokeShared(p)"
      >
        {{ t('settings.providerAuth.shared.revokeButton', { provider: p.label }) }}
      </BaseButton>
    </div>
    <p v-if="message" :class="['text-xs', isWarning ? 'text-autobot-error' : 'text-autobot-text-secondary']" role="status">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
// #19241 (owner decision 2026-10-23): superadmin-only revoke of the legacy LLM
// sign-in token every org may share. The backend gates it with
// require_role(Role.SUPERADMIN); this component is only rendered for superadmins.
import { BaseButton } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import { useSharedTokenRevoke } from '@/composables/useSharedTokenRevoke'
import type { ProviderInfo } from '@/utils/providerOAuth'

defineProps<{ providers: ProviderInfo[] }>()

const { t } = useI18n()
const { busy, message, isWarning, revokeShared } = useSharedTokenRevoke()
</script>
