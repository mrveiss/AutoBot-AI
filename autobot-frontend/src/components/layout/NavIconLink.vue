<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  NavIconLink — one icon-only header control (#18240): a router link for an
  internal entry, an <a target="_blank" rel="noopener noreferrer"> for an
  external one. The accessible name and the tooltip both come from the
  registry's i18n keys; the SVG is decorative.
-->
<template>
  <BaseTooltip :text="$t(item.tipKey)" placement="bottom" :class="{ adv: item.adv }">
    <template #default="{ describedby }">
      <a
        v-if="item.href"
        :href="item.href()"
        target="_blank"
        rel="noopener noreferrer"
        :class="linkClass"
        :aria-label="$t(item.ariaKey)"
        :aria-describedby="tipAddsInfo ? describedby : undefined"
      >
        <NavItemIcon :item="item" class="h-5 w-5" />
      </a>
      <router-link
        v-else
        :to="item.to ?? '/'"
        :class="[linkClass, active ? 'text-autobot-text-primary bg-autobot-bg-tertiary' : '']"
        :aria-label="$t(item.ariaKey)"
        :aria-describedby="tipAddsInfo ? describedby : undefined"
      >
        <NavItemIcon :item="item" class="h-5 w-5" />
      </router-link>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BaseTooltip } from '@autobot/ui'
import type { NavIconItem } from '@/config/navItems'
import NavItemIcon from '@/components/layout/NavItemIcon.vue'

const props = defineProps<{ item: NavIconItem }>()
const { t } = useI18n()
const route = useRoute()
const active = computed(() => !!props.item.to && route.path.startsWith(props.item.to))

// aria-label already names the control; describing it with the same words reads
// it twice. Link the tooltip only where it says something the name does not.
const norm = (v: string) => v.trim().toLowerCase()
const tipAddsInfo = computed(() => norm(t(props.item.tipKey)) !== norm(t(props.item.ariaKey)))

const linkClass =
  'inline-flex h-10 w-10 items-center justify-center rounded-lg text-autobot-text-secondary transition-colors duration-150 hover:bg-autobot-bg-tertiary hover:text-autobot-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary'
</script>
