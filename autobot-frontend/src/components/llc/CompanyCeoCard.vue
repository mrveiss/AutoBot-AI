<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #15945: the company CEO designation -- see it, change it, clear it.

  Shown in Company settings (the mockup's CEO section). Three states the backend keeps apart are
  kept apart here: no designation, a designation whose holder is gone, and a live holder. A refusal
  shows the server's own reason. Whether the viewer may change it is the server's call (it answers
  with a refusal); this does not guess a role locally. The holder is shown by name, the id second.
-->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, BaseSelectMenu, BaseSpinner } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { useCompanyPeople } from '@/composables/llc/useCompanyPeople'
import { ceoCandidates, parseCandidate, useCompanyCeo } from '@/composables/llc/useCompanyCeo'

const props = defineProps<{ companyId: string }>()
const { t } = useI18n()
const api = useApiClient()

const ceo = useCompanyCeo(api, () => props.companyId)
const { state, designation, isSaving, actionError } = ceo

const agents = ref<{ id: string; name: string }[]>([])
const people = ref<{ user_id: string; name: string }[]>([])
const peopleLoading = ref(false)
const peopleFailed = ref(false)

async function loadPeople(): Promise<void> {
  const source = useCompanyPeople(props.companyId)
  peopleLoading.value = true
  await source.load()
  agents.value = source.agents.value
  people.value = source.humans.value
  peopleFailed.value = source.loadFailed.value
  peopleLoading.value = false
}

const candidates = computed(() =>
  ceoCandidates(agents.value, people.value, (kind) => t(`llcSettings.ceo.kind.${kind}`)),
)

const picked = ref('')
const notice = ref('')

/** The current holder by name when the company's agents and people include it. */
const holder = computed(() => {
  const d = designation.value
  if (!d?.holder_id) return null
  const id = d.holder_id
  const name =
    d.holder_type === 'agent'
      ? agents.value.find((a) => a.id === id)?.name
      : people.value.find((p) => p.user_id === id)?.name
  return { id, kind: d.holder_type ?? '', name: name ?? null }
})

const kindText = computed(() => {
  const kind = holder.value?.kind
  return kind === 'agent' || kind === 'user' ? t(`llcSettings.ceo.kind.${kind}`) : ''
})

const errorText = computed(() => {
  if (actionError.value === null) return ''
  return actionError.value === '' ? t('llcSettings.ceo.actionFailed') : actionError.value
})

async function save(): Promise<void> {
  const body = parseCandidate(picked.value)
  if (!body) return
  notice.value = ''
  const name = candidates.value.find((c) => c.value === picked.value)?.label ?? ''
  if (await ceo.setCeo(body)) {
    notice.value = t('llcSettings.ceo.setDone', { name })
    picked.value = ''
  }
}

async function clear(): Promise<void> {
  notice.value = ''
  if (await ceo.clearCeo()) notice.value = t('llcSettings.ceo.clearDone')
}

function reloadAll(): void {
  void ceo.load()
  void loadPeople()
}

onMounted(reloadAll)
watch(
  () => props.companyId,
  () => {
    picked.value = ''
    notice.value = ''
    void loadPeople()
  },
)
</script>

<template>
  <BaseCard :title="t('llcSettings.ceo.title')" :subtitle="t('llcSettings.ceo.intro')" data-testid="company-ceo">
    <div class="flex flex-col gap-4">
      <div v-if="state === 'loading'" class="flex items-center gap-2 text-autobot-text-secondary" data-testid="ceo-loading">
        <BaseSpinner size="sm" :label="t('llcSettings.ceo.loading')" />
      </div>

      <BaseAlert v-else-if="state === 'failed'" variant="error" data-testid="ceo-failed">
        <div class="flex flex-wrap items-center gap-3">
          <span>{{ t('llcSettings.ceo.loadFailed') }}</span>
          <BaseButton variant="secondary" size="sm" @click="ceo.load()">{{ t('common.retry') }}</BaseButton>
        </div>
      </BaseAlert>

      <div
        v-else-if="state === 'none'"
        class="flex flex-wrap items-center gap-3 rounded border border-dashed border-autobot-border p-3"
        data-testid="ceo-none"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-1">
          <span class="font-semibold text-autobot-text-primary">{{ t('llcSettings.ceo.noneTitle') }}</span>
          <span class="text-autobot-text-secondary">{{ t('llcSettings.ceo.noneBody') }}</span>
        </div>
        <BaseBadge variant="neutral">{{ t('llcSettings.ceo.notSet') }}</BaseBadge>
      </div>

      <div
        v-else-if="state === 'gone'"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded border border-autobot-error bg-autobot-error-bg p-3"
        data-testid="ceo-gone"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-1 text-autobot-error">
          <span class="font-semibold">{{ t('llcSettings.ceo.goneTitle') }}</span>
          <span>{{ t('llcSettings.ceo.goneBody', { id: holder?.id ?? '' }) }}</span>
        </div>
        <BaseBadge variant="error">{{ t('llcSettings.ceo.goneBadge') }}</BaseBadge>
      </div>

      <div
        v-else
        class="flex flex-wrap items-center gap-3 rounded border border-autobot-border p-3"
        data-testid="ceo-live"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-1">
          <span class="font-semibold text-autobot-text-primary" data-testid="ceo-name">{{
            holder?.name ?? t('llcSettings.ceo.nameUnavailable')
          }}</span>
          <span class="break-all text-autobot-text-muted">{{ kindText }} · {{ holder?.id }}</span>
        </div>
        <BaseBadge variant="success">{{ t('llcSettings.ceo.current') }}</BaseBadge>
      </div>

      <BaseAlert v-if="peopleFailed" variant="warning" :message="t('llcSettings.ceo.peopleFailed')" data-testid="ceo-people-failed" />

      <div class="flex flex-col gap-2">
        <span class="font-semibold text-autobot-text-primary">{{ t('llcSettings.ceo.change') }}</span>
        <BaseSelectMenu
          v-model="picked"
          :options="candidates"
          :label="t('llcSettings.ceo.change')"
          :placeholder="peopleLoading ? t('llcSettings.ceo.loadingPeople') : t('llcSettings.ceo.pick')"
          :disabled="peopleLoading || isSaving || candidates.length === 0"
        />
        <p v-if="!peopleLoading && !peopleFailed && candidates.length === 0" class="m-0 text-autobot-text-muted" data-testid="ceo-no-candidates">
          {{ t('llcSettings.ceo.noCandidates') }}
        </p>
        <p v-else class="m-0 text-autobot-text-muted">{{ t('llcSettings.ceo.hint') }}</p>
      </div>

      <BaseAlert v-if="errorText" variant="error" :message="errorText" data-testid="ceo-error" />
      <p v-if="notice" class="m-0 text-autobot-text-secondary" role="status" data-testid="ceo-notice">{{ notice }}</p>

      <div class="flex flex-wrap gap-2">
        <BaseButton variant="primary" :loading="isSaving" :disabled="!picked || isSaving" data-testid="ceo-set" @click="save">
          {{ t('llcSettings.ceo.set') }}
        </BaseButton>
        <BaseButton
          variant="error"
          :disabled="isSaving || state === 'none' || state === 'loading' || state === 'failed'"
          data-testid="ceo-clear"
          @click="clear"
        >
          {{ t('llcSettings.ceo.clear') }}
        </BaseButton>
      </div>
    </div>
  </BaseCard>
</template>
