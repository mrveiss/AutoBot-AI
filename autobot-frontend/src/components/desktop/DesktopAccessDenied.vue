<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Shown where a desktop viewer would be, to a caller the socket will refuse
  (#17370). One component rather than the message repeated at each of the four
  render sites.

  This is NOT the access boundary -- `enforce_ws_desktop_auth` is, and #17369
  closed it. This exists so a refused caller reads an explanation instead of a
  viewer that never connects, or a control that silently is not there.

  Styled by the canonical `.empty-state` set in `assets/css/components.css`,
  with no `<style>` block of its own. The first version hand-rolled
  `.desktop-denied{,-icon,-title,-desc}` -- a second implementation of a
  four-part component the design system already had. That is a
  canonical-design-system violation on its own, and it also pushed three
  frontend-fragmentation ratchets over their pins (#12730, #12731).
-->
<template>
  <div class="empty-state" role="status">
    <Icon name="lock" class="empty-state-icon" />
    <p class="empty-state-title">{{ t('desktop.accessDenied.title') }}</p>
    <p class="empty-state-desc">{{ t('desktop.accessDenied.description') }}</p>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
</script>
