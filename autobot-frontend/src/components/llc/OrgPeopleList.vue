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

import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UNGROUPED_TEAM_ID, contactIdOfKey } from '@/composables/llc/orgPeople'
import type { ContactEditPatch, OrgPeopleGroup, OrgPerson, PersonKind } from '@/composables/llc/orgPeople'

const props = defineProps<{
  groups: OrgPeopleGroup[]
  counts: Record<PersonKind, number>
  /** Whether the company has any team at all — drives the honest empty state. */
  hasTeams: boolean
  /**
   * A source that did not answer. Absence of data and absence of an answer are
   * different claims, and this list must never make the first one on behalf of
   * the second (#14064): "no teams are defined" is a statement about the
   * company, and we only know it when the request actually succeeded.
   */
  teamsFailed?: boolean
  contactsFailed?: boolean
  /**
   * Contact ids this department carries with no role to explain them (#13998).
   *
   * Labelled rather than merged or hidden: merging asserts an involvement
   * nobody recorded, hiding makes people vanish from a department already using
   * them. The label is what prompts someone to assign the role — and the group
   * empties itself as that happens.
   */
  unassignedContactIds?: Set<string>
  /**
   * The contact id a save is in flight for (#14603) — never a plain boolean,
   * so a row that is not the one being saved keeps its inputs live rather
   * than every open editor freezing for one row's request.
   */
  savingContactId?: string | null
  /**
   * The most recent save failure, scoped to the contact it was for (#14603).
   * Scoping it this way means a failure on one row can never render against a
   * different row that has since been opened for editing.
   */
  contactSaveError?: { contactId: string; message: string } | null
}>()

const emit = defineEmits<{
  select: [orgNodeId: string]
  /** A contact's edit form was submitted — the parent owns the PATCH and the refetch (#14603). */
  'save-contact': [contactId: string, patch: ContactEditPatch]
}>()

/** True when no role explains this person's presence in the department. */
function isUnassigned(person: { key: string; kind: string }): boolean {
  if (person.kind !== 'contact') return false
  return props.unassignedContactIds?.has(contactIdOfKey(person.key)) ?? false
}

// #14603: contact editing, in place in the row. Only a contact ever reaches
// this state — a user edits their own profile, and an agent's title has no
// write endpoint yet (see the issue's second comment) — so every helper below
// is a no-op for `kind !== 'contact'` rather than trusting the caller.

/** The person key of the row currently open for editing — one at a time. */
const editingKey = ref<string | null>(null)

/** Draft field values for the open row, reset each time editing starts. */
const draft = reactive<ContactEditPatch>({ full_name: '', role_title: '', email: '', phone: '' })

function isEditingContact(person: { key: string; kind: string }): boolean {
  return person.kind === 'contact' && editingKey.value === person.key
}

function isSavingContact(person: { key: string; kind: string }): boolean {
  return person.kind === 'contact' && props.savingContactId === contactIdOfKey(person.key)
}

/** The save error for this exact row, or null — never another row's error. */
function contactErrorFor(person: { key: string; kind: string }): string | null {
  if (person.kind !== 'contact' || !props.contactSaveError) return null
  return props.contactSaveError.contactId === contactIdOfKey(person.key)
    ? props.contactSaveError.message
    : null
}

function startEditingContact(person: OrgPerson): void {
  if (person.kind !== 'contact') return
  editingKey.value = person.key
  draft.full_name = person.name
  draft.role_title = person.subtitle
  draft.email = person.contactEmail ?? ''
  draft.phone = person.contactPhone ?? ''
}

function cancelEditingContact(): void {
  editingKey.value = null
}

function submitContactEdit(person: { key: string; kind: string }): void {
  if (person.kind !== 'contact') return
  emit('save-contact', contactIdOfKey(person.key), {
    full_name: draft.full_name.trim(),
    role_title: draft.role_title.trim(),
    email: draft.email.trim(),
    phone: draft.phone.trim(),
  })
}

// Close the editor once the save the open row was waiting on finishes
// successfully. A failure is reported through `contactSaveError` and the
// editor stays open with the typed draft intact (#14603) — closing on
// failure would discard the very input someone would want to retry with.
watch(
  () => props.savingContactId,
  (savingId, previousSavingId) => {
    if (savingId !== null) return
    if (!previousSavingId || !editingKey.value) return
    if (contactIdOfKey(editingKey.value) !== previousSavingId) return
    if (props.contactSaveError?.contactId === previousSavingId) return
    editingKey.value = null
  },
)

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

    <p v-if="teamsFailed" class="text-xs text-autobot-text-muted" data-testid="org-people-teams-unavailable">
      {{ t('llc.orgChart.peopleTeamsUnavailable') }}
    </p>
    <p v-else-if="!hasTeams" class="text-xs text-autobot-text-muted" data-testid="org-people-no-teams">
      {{ t('llc.orgChart.peopleNoTeamsDefined') }}
    </p>
    <p v-else class="text-xs text-autobot-text-muted" data-testid="org-people-teams-note">
      {{ t('llc.orgChart.peopleTeamsCoverUsersOnly') }}
    </p>

    <p
      v-if="totalPeople === 0 && (contactsFailed || teamsFailed)"
      class="py-8 text-center text-autobot-text-muted"
      data-testid="org-people-unavailable"
    >
      {{ t('llc.orgChart.peopleUnavailable') }}
    </p>

    <p
      v-else-if="totalPeople === 0"
      class="py-8 text-center text-autobot-text-muted"
      data-testid="org-people-empty"
    >
      {{ t('llc.orgChart.peopleEmpty') }}
    </p>

    <template v-if="totalPeople > 0">
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

            <!-- #14603: only a contact ever reaches edit mode — a user edits
                 their own profile, and an agent's title has no write endpoint
                 yet (see the issue's decision). The form below replaces the
                 read view for exactly this row; every other row is untouched. -->
            <form
              v-if="isEditingContact(person)"
              class="flex min-w-0 flex-1 flex-wrap items-end gap-2"
              :data-testid="`org-person-edit-form-${person.key}`"
              @submit.prevent="submitContactEdit(person)"
            >
              <label class="flex min-w-0 flex-col text-xs text-autobot-text-muted">
                {{ t('llc.orgPeople.fullNameLabel') }}
                <input
                  v-model="draft.full_name"
                  type="text"
                  required
                  class="rounded border border-autobot-border bg-autobot-bg-primary px-2 py-1 text-sm text-autobot-text-primary"
                  :data-testid="`org-person-edit-name-${person.key}`"
                  :disabled="isSavingContact(person)"
                />
              </label>
              <label class="flex min-w-0 flex-col text-xs text-autobot-text-muted">
                {{ t('llc.orgPeople.roleTitleLabel') }}
                <input
                  v-model="draft.role_title"
                  type="text"
                  class="rounded border border-autobot-border bg-autobot-bg-primary px-2 py-1 text-sm text-autobot-text-primary"
                  :data-testid="`org-person-edit-role-${person.key}`"
                  :disabled="isSavingContact(person)"
                />
              </label>
              <label class="flex min-w-0 flex-col text-xs text-autobot-text-muted">
                {{ t('llc.orgPeople.emailLabel') }}
                <input
                  v-model="draft.email"
                  type="email"
                  class="rounded border border-autobot-border bg-autobot-bg-primary px-2 py-1 text-sm text-autobot-text-primary"
                  :data-testid="`org-person-edit-email-${person.key}`"
                  :disabled="isSavingContact(person)"
                />
              </label>
              <label class="flex min-w-0 flex-col text-xs text-autobot-text-muted">
                {{ t('llc.orgPeople.phoneLabel') }}
                <input
                  v-model="draft.phone"
                  type="text"
                  class="rounded border border-autobot-border bg-autobot-bg-primary px-2 py-1 text-sm text-autobot-text-primary"
                  :data-testid="`org-person-edit-phone-${person.key}`"
                  :disabled="isSavingContact(person)"
                />
              </label>
              <button
                type="submit"
                class="rounded border border-autobot-primary px-2 py-1 text-xs font-semibold text-autobot-primary disabled:opacity-50"
                :data-testid="`org-person-edit-save-${person.key}`"
                :disabled="isSavingContact(person) || !draft.full_name.trim()"
              >
                {{ isSavingContact(person) ? t('llc.orgPeople.saving') : t('llc.orgPeople.save') }}
              </button>
              <button
                type="button"
                class="rounded border border-autobot-border px-2 py-1 text-xs text-autobot-text-muted"
                :data-testid="`org-person-edit-cancel-${person.key}`"
                :disabled="isSavingContact(person)"
                @click="cancelEditingContact()"
              >
                {{ t('common.cancel') }}
              </button>
              <span
                v-if="contactErrorFor(person)"
                class="block w-full text-xs text-autobot-error"
                :data-testid="`org-person-edit-error-${person.key}`"
              >
                {{ contactErrorFor(person) }}
              </span>
            </form>

            <span v-else class="min-w-0 flex-1">
              <!-- A hierarchy member opens the same drawer the tree opens; a
                   contact has no org-chart node, so it is plain text. -->
              <button
                v-if="person.orgNodeId"
                type="button"
                class="truncate text-sm font-medium text-autobot-text-primary hover:text-autobot-text-link"
                :data-testid="`org-person-open-${person.key}`"
                @click="emit('select', person.orgNodeId)"
              >
                {{ person.name }}
              </button>
              <span v-else class="block truncate text-sm font-medium text-autobot-text-primary">
                {{ person.name }}
              </span>
              <!-- Outside both name branches: a contact renders through the
                   v-else above (it has no org-chart node), so a badge nested in
                   the button branch is unreachable for exactly the people it
                   describes. -->
              <span
                v-if="isUnassigned(person)"
                class="person-unassigned"
                :data-testid="`org-person-unassigned-${person.key}`"
                :title="t('llc.orgPeople.unassignedHint')"
              >
                {{ t('llc.orgPeople.unassigned') }}
              </span>
              <!-- #13956: shown, not filtered. Someone who has left keeps the
                   work items and the role they held, so removing them from the
                   chart would leave those with no visible owner. The badge is
                   what stops "still listed" reading as "still available". -->
              <span
                v-if="person.isInactive"
                class="ms-2 rounded-full border border-autobot-text-muted px-2 py-0.5 text-xs text-autobot-text-muted"
                :data-testid="`org-person-inactive-${person.key}`"
                :title="t('llc.orgPeople.inactiveHint')"
              >
                {{ t('llc.orgPeople.inactive') }}
              </span>
              <span v-if="person.subtitle" class="block truncate text-xs text-autobot-text-muted">
                {{ person.subtitle }}
              </span>
            </span>
            <span v-if="!isEditingContact(person) && person.channel" class="truncate text-xs text-autobot-text-muted">
              {{ person.channel }}
            </span>
            <!-- #14603: contact-only affordance. A user edits their own
                 profile and an agent's title has no write path here, so
                 neither kind ever renders this button — asserted directly by
                 the People-list contact-edit tests. -->
            <button
              v-if="!isEditingContact(person) && person.kind === 'contact'"
              type="button"
              class="shrink-0 rounded border border-autobot-border px-2 py-1 text-xs text-autobot-text-muted hover:text-autobot-text-primary"
              :data-testid="`org-person-edit-${person.key}`"
              :aria-label="t('llc.orgPeople.editAriaLabel', { name: person.name })"
              @click="startEditingContact(person)"
            >
              {{ t('common.edit') }}
            </button>
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
