<script setup lang="ts">
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The Org Chart's People list (#13938): teams and people of all three kinds —
// agent, user, contact — in the surface whose job is to show the organisation.
//
// Contacts appear here and nowhere else in this view: they are not hierarchy
// members (no reports_to, no budget, no heartbeat), so they never reach the
// nested tree or the canvas. The list states that in words rather than leaving
// the flat layout to imply it.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { UNGROUPED_TEAM_ID } from '@/composables/llc/orgPeople'
import type { OrgPeopleGroup, PersonKind } from '@/composables/llc/orgPeople'

const props = defineProps<{
  groups: OrgPeopleGroup[]
  counts: Record<PersonKind, number>
  /** Whether the company has any team at all — drives the honest empty state. */
  hasTeams: boolean
}>()

const emit = defineEmits<{ select: [orgNodeId: string] }>()

const { t } = useI18n()

/** Stable display order, so a kind never moves between renders. */
const KIND_ORDER: readonly PersonKind[] = ['agent', 'user', 'contact'] as const

/**
 * One design token per kind — the visual distinction the three kinds need.
 * Tokens only (`design-system/tokens.ts`), never a literal colour.
 */
const KIND_BADGE_CLASS: Record<PersonKind, string> = {
  agent: 'bg-autobot-primary-bg text-autobot-primary border-autobot-primary',
  user: 'bg-autobot-info-bg text-autobot-info border-autobot-info',
  contact: 'bg-autobot-warning-bg text-autobot-warning border-autobot-warning',
}

const totalPeople = computed(() =>
  KIND_ORDER.reduce((sum, kind) => sum + (props.counts[kind] ?? 0), 0),
)

function kindLabel(kind: PersonKind): string {
  return t(`llc.orgChart.peopleKind.${kind}`)
}

function kindHint(kind: PersonKind): string {
  return t(`llc.orgChart.peopleKindHint.${kind}`)
}

function groupLabel(group: OrgPeopleGroup): string {
  return group.id === UNGROUPED_TEAM_ID ? t('llc.orgChart.peopleNoTeam') : group.name
}
</script>

<template>
  <section data-testid="org-people" class="space-y-4">
    <!-- Legend: the three kinds, named and counted, with what each one is. -->
    <div
      class="flex flex-wrap items-center gap-3 rounded-lg border border-autobot-border bg-autobot-bg-card p-3"
      data-testid="org-people-legend"
      :aria-label="t('llc.orgChart.peopleLegend')"
    >
      <span
        v-for="kind in KIND_ORDER"
        :key="kind"
        class="inline-flex items-center gap-2 text-xs"
        :data-testid="`org-people-legend-${kind}`"
      >
        <span class="rounded-full border px-2 py-0.5 font-semibold" :class="KIND_BADGE_CLASS[kind]">
          {{ kindLabel(kind) }}
        </span>
        <span class="text-autobot-text-muted">{{ kindHint(kind) }} · {{ counts[kind] ?? 0 }}</span>
      </span>
    </div>

    <p v-if="!hasTeams" class="text-xs text-autobot-text-muted" data-testid="org-people-no-teams">
      {{ t('llc.orgChart.peopleNoTeamsDefined') }}
    </p>
    <p v-else class="text-xs text-autobot-text-muted" data-testid="org-people-teams-note">
      {{ t('llc.orgChart.peopleTeamsCoverUsersOnly') }}
    </p>

    <p
      v-if="totalPeople === 0"
      class="py-8 text-center text-autobot-text-muted"
      data-testid="org-people-empty"
    >
      {{ t('llc.orgChart.peopleEmpty') }}
    </p>

    <template v-else>
      <div
        v-for="group in groups"
        :key="group.id"
        class="rounded-lg border border-autobot-border"
        :data-testid="`org-people-group-${group.id}`"
      >
        <h3
          v-if="hasTeams"
          class="border-b border-autobot-border px-4 py-2 text-sm font-semibold text-autobot-text-primary"
        >
          {{ groupLabel(group) }}
        </h3>
        <p
          v-if="group.people.length === 0"
          class="px-4 py-3 text-xs text-autobot-text-muted"
          :data-testid="`org-people-group-empty-${group.id}`"
        >
          {{ t('llc.orgChart.peopleTeamEmpty') }}
        </p>
        <ul v-else class="divide-y divide-autobot-border">
          <li
            v-for="person in group.people"
            :key="person.key"
            class="flex items-center gap-3 px-4 py-2"
            :data-testid="`org-person-${person.key}`"
          >
            <span
              class="rounded-full border px-2 py-0.5 text-xs font-semibold"
              :class="KIND_BADGE_CLASS[person.kind]"
              :data-testid="`org-person-kind-${person.key}`"
            >
              {{ kindLabel(person.kind) }}
            </span>
            <span class="min-w-0 flex-1">
              <!-- A hierarchy member opens the same drawer the tree opens; a
                   contact has no org-chart node, so it is plain text. -->
              <button
                v-if="person.orgNodeId"
                type="button"
                class="truncate text-sm font-medium text-autobot-text-primary hover:text-autobot-text-link"
                @click="emit('select', person.orgNodeId)"
              >
                {{ person.name }}
              </button>
              <span v-else class="block truncate text-sm font-medium text-autobot-text-primary">
                {{ person.name }}
              </span>
              <span v-if="person.subtitle" class="block truncate text-xs text-autobot-text-muted">
                {{ person.subtitle }}
              </span>
            </span>
            <span v-if="person.channel" class="truncate text-xs text-autobot-text-muted">
              {{ person.channel }}
            </span>
          </li>
        </ul>
      </div>
    </template>

    <p
      v-if="counts.contact > 0"
      class="text-xs text-autobot-text-muted"
      data-testid="org-people-contact-note"
    >
      {{ t('llc.orgChart.peopleContactNotInHierarchy') }}
    </p>
  </section>
</template>
