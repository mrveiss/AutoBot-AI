<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  MailboxView -- Company OS > Mailbox (#13714, mockups CompanyMailbox / Mailbox).
  The mailbox backend (connector, router, sanitised bodies, compose, risk tier) is
  not built, so this screen says so plainly: no rows, no compose controls and no
  API call until a mailbox route exists to call.
-->
<template>
  <div class="flex flex-col gap-4 p-4" data-testid="company-mailbox">
    <header class="flex flex-wrap items-baseline gap-3">
      <h1 class="m-0 text-xl text-autobot-text-primary">{{ t('llc.mailbox.title') }}</h1>
      <p class="m-0 text-autobot-text-secondary">{{ t('llc.mailbox.subtitle') }}</p>
    </header>
    <EmptyState
      data-testid="mailbox-unavailable"
      :title="t('llc.mailbox.unavailableTitle')"
      :description="t('llc.mailbox.unavailableBody')"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EmptyState } from '@autobot/ui'

const { t } = useI18n()
</script>
