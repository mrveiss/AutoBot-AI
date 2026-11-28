<template>
  <div class="flex flex-col gap-5">
    <p v-if="loadError" class="text-sm text-autobot-error" role="alert">{{ loadError }}</p>
    <template v-else>
      <div v-if="isAdmin" class="provider-scope-section" data-testid="provider-section-system">
        <h4 class="text-sm font-semibold text-autobot-text-primary">{{ t('settings.providerAuth.systemHeading') }}</h4>
        <p class="mb-2 text-xs text-autobot-text-muted">{{ t('settings.providerAuth.systemDesc') }}</p>
        <div class="flex flex-col gap-4">
          <ProviderOAuthConnect
            v-for="p in providers"
            :key="`system-${p.name}`"
            scope="system"
            :can-revoke-shared="isSuperadmin"
            :provider-name="p.name"
            :provider-label="p.label"
            :flows="p.flows"
            :configured="p.configured"
            :missing-settings="p.missing_settings"
          >
            <template #apikey>
              <p class="apikey-hint">{{ t('settings.providerAuth.apiKeyHint') }}</p>
            </template>
          </ProviderOAuthConnect>
        </div>
        <SharedTokenRevoke v-if="isSuperadmin" :providers="providers" />
      </div>

      <div class="provider-scope-section" data-testid="provider-section-user">
        <h4 class="text-sm font-semibold text-autobot-text-primary">{{ t('settings.providerAuth.userHeading') }}</h4>
        <p class="mb-2 text-xs text-autobot-text-muted">{{ t('settings.providerAuth.userDesc') }}</p>
        <div class="flex flex-col gap-4">
          <ProviderOAuthConnect
            v-for="p in providers"
            :key="`user-${p.name}`"
            scope="user"
            :provider-name="p.name"
            :provider-label="p.label"
            :flows="p.flows"
            :configured="p.configured"
            :missing-settings="p.missing_settings"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import ProviderOAuthConnect from '@/components/settings/ProviderOAuthConnect.vue'
import SharedTokenRevoke from '@/components/settings/SharedTokenRevoke.vue'
import { isSuperadminRole } from '@/constants/roles'
import { useUserStore } from '@/stores/useUserStore'
import type { ProviderInfo } from '@/utils/providerOAuth'
import type { components } from '@/types/generated/api'

defineProps<{ isAdmin: boolean }>()

const logger = createLogger('ProviderAccountsSection')
const { t } = useI18n()
const providers = ref<ProviderInfo[]>([])
// #19241: the shared-token revoke is superadmin-only (backend: require_role(Role.SUPERADMIN)).
const userStore = useUserStore()
const isSuperadmin = computed(() => isSuperadminRole(userStore.currentUser?.role))
const loadError = ref('')

onMounted(async () => {
  try {
    const listing: components['schemas']['ProviderListing'][] = await ApiClient.get('/api/llm-auth/providers')
    providers.value = listing
  } catch (err: unknown) {
    logger.error('Failed to load provider list', err)
    loadError.value = t('settings.providerAuth.loadFailed')
  }
})
</script>
