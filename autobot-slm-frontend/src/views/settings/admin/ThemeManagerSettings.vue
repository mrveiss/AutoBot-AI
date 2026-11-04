<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ThemeManagerSettings -- SLM > Settings > Themes, admin only (#20605). The theme packages the main
  backend's /themes routes hold: the installed list (GET), install from a .zip (POST, multipart) and
  uninstall behind a confirmation (DELETE). It moved here from the main app's /slm/themes view.

  Said apart, never folded into "nothing": reading, failed, main app not available, and none
  installed. A refused upload says why: not a .zip, larger than the proxy takes, or not an admin.
-->
<template>
  <div class="flex flex-col gap-4 p-4 text-(--aui-color-text)" data-testid="slm-themes">
    <header class="flex flex-wrap items-baseline gap-3">
      <h2 class="m-0 text-xl font-semibold">{{ t(`${NS}.title`) }}</h2>
      <p class="m-0 text-(--aui-color-text-muted)">{{ t(`${NS}.subtitle`) }}</p>
      <BaseButton class="ms-auto" variant="secondary" size="sm" :loading="state === 'loading'" data-testid="slm-themes-refresh" @click="load">
        {{ t(`${NS}.refresh`) }}
      </BaseButton>
    </header>

    <BaseAlert v-if="notice" :variant="notice.variant" :message="notice.text" dismissible :dismiss-label="t(`${NS}.dismiss`)" data-testid="slm-themes-notice" @dismiss="notice = null" />

    <p v-if="state === 'loading' && !loaded" role="status" class="m-0 flex items-center gap-2 text-(--aui-color-text-muted)" data-testid="slm-themes-loading">
      <BaseSpinner size="sm" />{{ t(`${NS}.loading`) }}
    </p>
    <BaseAlert v-else-if="state === 'unavailable'" variant="warning" :title="t(`${NS}.unavailableTitle`)" :message="t(`${NS}.unavailableBody`)" data-testid="slm-themes-unavailable" />
    <BaseAlert v-else-if="state === 'error'" variant="error" :title="t(`${NS}.errorTitle`)" :message="errorText" data-testid="slm-themes-error" />

    <template v-else>
      <BaseCard :title="t(`${NS}.installTitle`)" data-testid="slm-themes-install">
        <p class="m-0 mb-3 text-(--aui-color-text-muted)">{{ t(`${NS}.installHint`) }}</p>
        <input ref="fileInput" type="file" accept=".zip" class="hidden" data-testid="slm-themes-file" @change="onFile" />
        <BaseButton variant="primary" :loading="installing" data-testid="slm-themes-choose" @click="chooseFile">
          {{ t(`${NS}.${installing ? 'installing' : 'chooseFile'}`) }}
        </BaseButton>
      </BaseCard>

      <EmptyState v-if="rows.length === 0" :title="t(`${NS}.emptyTitle`)" :description="t(`${NS}.emptyBody`)" data-testid="slm-themes-empty" />
      <BaseCard v-else :title="t(`${NS}.tableLabel`)">
        <BaseTable :columns="columns" :rows="rows" row-key="id" :aria-label="t(`${NS}.tableLabel`)" :actions-label="t(`${NS}.actions`)" data-testid="slm-themes-table">
          <template #actions="{ row }">
            <BaseButton variant="secondary" size="sm" :data-testid="`slm-themes-uninstall-${row.id}`" @click="askRemove(row.id)">{{ t(`${NS}.uninstall`) }}</BaseButton>
          </template>
        </BaseTable>
      </BaseCard>
    </template>

    <BaseModal v-model="confirmOpen" :title="t(`${NS}.confirmTitle`, { name: pendingName })" size="sm" :close-label="t('ui.modal.closeDialog')">
      <p class="m-0" data-testid="slm-themes-confirm-body">{{ t(`${NS}.confirmBody`) }}</p>
      <template #actions>
        <BaseButton variant="secondary" data-testid="slm-themes-confirm-cancel" @click="confirmOpen = false">{{ t(`${NS}.confirmCancel`) }}</BaseButton>
        <BaseButton variant="error" :loading="removing" data-testid="slm-themes-confirm-remove" @click="remove">{{ t(`${NS}.uninstall`) }}</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { isHttpError, BaseAlert, BaseButton, BaseCard, BaseModal, BaseSpinner, BaseTable, EmptyState, type BaseTableColumn } from '@autobot/ui'
import { autobotApiErrorMessage } from '@/composables/autobotApiError'
import { isMainAppUnavailable, useThemesApi, UPLOAD_TOO_LARGE_STATUS, type InstalledTheme } from '@/composables/useThemesApi'

type LoadState = 'loading' | 'ready' | 'error' | 'unavailable'
type FileInputRef = HTMLInputElement | null
interface Notice { variant: 'success' | 'error'; text: string }

const NS = 'settings.admin.themeManager'
const ZIP_NAME = /\.zip$/i
const FORBIDDEN_STATUSES = [401, 403]
const { t } = useI18n()
const api = useThemesApi()

const state = ref<LoadState>('loading')
const errorText = ref('')
const themes = ref([] as InstalledTheme[])
const loaded = ref(false)
const notice = ref(null as Notice | null)
const fileInput = ref<FileInputRef>(null)
const installing = ref(false)
const confirmOpen = ref(false)
const pendingId = ref('')
const removing = ref(false)

const columns = computed(() => [
  { key: 'name', label: t(`${NS}.col.name`) },
  { key: 'version', label: t(`${NS}.col.version`), monospace: true },
  { key: 'author', label: t(`${NS}.col.author`) },
  { key: 'supports', label: t(`${NS}.col.supports`) },
  { key: 'id', label: t(`${NS}.col.id`), monospace: true },
] as BaseTableColumn[])
const rows = computed(() => themes.value.map((theme) => ({ ...theme, supports: theme.supports.join(', ') })))
const pendingName = computed(() => themes.value.find((theme) => theme.id === pendingId.value)?.name ?? pendingId.value)

async function load(): Promise<void> {
  state.value = 'loading'
  try {
    themes.value = await api.list()
  } catch (e) {
    const unavailable = isMainAppUnavailable(e)
    errorText.value = autobotApiErrorMessage(e, t(`${NS}.errorBody`))
    state.value = unavailable ? 'unavailable' : 'error'
    return
  }
  loaded.value = true
  state.value = 'ready'
}

/** The reason a write failed, in words: the proxy's size cap, a non-admin session, the main app down, else the backend's own detail. */
function failureText(e: unknown, fallback: string): string {
  if (isHttpError(e) && e.status === UPLOAD_TOO_LARGE_STATUS) return t(`${NS}.tooLarge`)
  if (isHttpError(e) && FORBIDDEN_STATUSES.includes(e.status)) return t(`${NS}.adminOnly`)
  if (isMainAppUnavailable(e)) return t(`${NS}.unavailableBody`)
  return autobotApiErrorMessage(e, fallback)
}

function chooseFile(): void {
  fileInput.value?.click()
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || installing.value) return
  notice.value = null
  if (!ZIP_NAME.test(file.name)) {
    notice.value = { variant: 'error', text: t(`${NS}.notZip`) }
    return
  }
  installing.value = true
  try {
    const installed = await api.install(file)
    notice.value = { variant: 'success', text: t(`${NS}.installedOk`, { name: installed.name, version: installed.version }) }
  } catch (e) {
    notice.value = { variant: 'error', text: failureText(e, t(`${NS}.installFailed`)) }
    installing.value = false
    return
  }
  installing.value = false
  await load()
}

function askRemove(id: string): void {
  pendingId.value = id
  confirmOpen.value = true
}

async function remove(): Promise<void> {
  if (removing.value) return
  removing.value = true
  notice.value = null
  const name = pendingName.value
  try {
    await api.uninstall(pendingId.value)
    notice.value = { variant: 'success', text: t(`${NS}.removedOk`, { name }) }
  } catch (e) {
    notice.value = { variant: 'error', text: failureText(e, t(`${NS}.removeFailed`)) }
    removing.value = false
    confirmOpen.value = false
    return
  }
  removing.value = false
  confirmOpen.value = false
  await load()
}

onMounted(load)
</script>
