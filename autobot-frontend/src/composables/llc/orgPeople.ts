// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The Org Chart's People model — the three kinds of person a company has (#13938).
 *
 * ## Why three kinds out of a two-valued flag
 *
 * The org-chart endpoint reports `is_human: boolean` (#13936). That flag cannot
 * express three kinds, and inventing a fourth vocabulary for the actor axis is
 * exactly what #13970 exists to stop — `CoWorkerType {agent, human}` and
 * `AssigneeType {user, agent}` already fork one axis under different member
 * names, which produced the live bug #13954.
 *
 * So the kind is not read from a new field; it is read from **provenance plus
 * the existing flag**, and no backend discriminator is added:
 *
 *   | source                          | `is_human` | kind      |
 *   |---------------------------------|------------|-----------|
 *   | `/companies/{id}/org-chart`     | `false`    | `agent`   |
 *   | `/companies/{id}/org-chart`     | `true`     | `user`    |
 *   | `/contacts/{id}`                | n/a        | `contact` |
 *
 * A contact can only ever come from `llc_contacts`, and `llc_contacts` is never
 * queried by `get_org_chart` (enforced in that model's docstring and by
 * `llc/tests/test_contact_no_login.py`), so provenance is a total function on
 * the three kinds — there is no row that two branches could both claim.
 *
 * ## Vocabulary choice (#13970)
 *
 * The member names below are `AssigneeType {user, agent}` extended with
 * `contact`, **not** `CoWorkerType {agent, human}`. Justification: a contact is
 * also a human, so `human` stops discriminating the moment the third kind
 * exists, while `user` keeps naming exactly one thing — the account holder,
 * i.e. a `users` row. That is the vocabulary that survives the axis becoming
 * three-valued, which is the requirement #13970 states. This module does not
 * settle #13970 (that is a backend enum change with call sites to migrate); it
 * picks the surviving vocabulary so the frontend does not become a fourth fork.
 */

/** The three kinds of person a company has. See the module docstring. */
export type PersonKind = 'agent' | 'user' | 'contact'

/** The org-chart node fields this module reads — a structural subset of `OrgNode`. */
export interface OrgChartPersonSource {
  id: string
  name: string
  title: string
  is_human: boolean
  children?: OrgChartPersonSource[]
}

/** The contact fields this module reads — a structural subset of `ContactResponse`. */
export interface ContactSource {
  id: string
  full_name: string
  role_title?: string | null
  email?: string | null
  phone?: string | null
}

/** One team of the company, as `/companies/{id}/teams` reports it (#13938). */
export interface CompanyTeam {
  id: string
  name: string
  member_user_ids: string[]
}

/** A person of any kind, as the People list renders them. */
export interface OrgPerson {
  /** Unique within the list — org-chart ids are already namespaced (`user:<uuid>`). */
  key: string
  kind: PersonKind
  name: string
  /** Role/title line: membership role, agent title, or the contact's free-text role. */
  subtitle: string
  /** Process contact channel — contacts only; a user's email is not exposed here. */
  channel: string | null
  /** `users.id` for a `user` kind — the key team membership is expressed in. */
  userId: string | null
  /** The org-chart node id, so a click can open the same drawer the tree opens. */
  orgNodeId: string | null
}

/** A team's people, or the honest "not in a team" bucket. */
export interface OrgPeopleGroup {
  /** Team id, or `UNGROUPED_TEAM_ID` for the people no team claims. */
  id: string
  /** Team name — empty for the ungrouped bucket, which the view labels itself. */
  name: string
  people: OrgPerson[]
}

/**
 * The bucket for people no team claims. Not a fabricated team: it is named for
 * the absence of a team, and it is the *only* place agents and contacts can
 * land, because `teams`/`team_memberships` key on `users.id` and neither
 * `agent_org_nodes` nor `llc_contacts` has one.
 */
export const UNGROUPED_TEAM_ID = '__no_team__'

/** The kind of an org-chart node — see the module docstring's provenance table. */
export function personKindOfOrgNode(node: Pick<OrgChartPersonSource, 'is_human'>): PersonKind {
  return node.is_human ? 'user' : 'agent'
}

/** `user:<uuid>` → `<uuid>`; anything else has no `users` row behind it. */
const USER_NODE_PREFIX = 'user:'

function userIdOf(node: OrgChartPersonSource): string | null {
  if (!node.is_human) return null
  return node.id.startsWith(USER_NODE_PREFIX) ? node.id.slice(USER_NODE_PREFIX.length) : null
}

/** Flatten the org-chart forest into people, parents before children. */
function collectOrgPeople(nodes: OrgChartPersonSource[], out: OrgPerson[]): void {
  for (const node of nodes) {
    out.push({
      key: node.id,
      kind: personKindOfOrgNode(node),
      name: node.name,
      subtitle: node.title,
      channel: null,
      userId: userIdOf(node),
      orgNodeId: node.id,
    })
    if (node.children?.length) collectOrgPeople(node.children, out)
  }
}

/**
 * Every person of the company, of all three kinds, in one list.
 *
 * Contacts are appended, never merged into the forest: they carry no
 * `reports_to`, no budget and no heartbeat, so putting them in the reporting
 * tree would assert a reporting relationship that does not exist (#13938).
 */
export function buildOrgPeople(
  orgNodes: OrgChartPersonSource[],
  contacts: ContactSource[],
): OrgPerson[] {
  const people: OrgPerson[] = []
  collectOrgPeople(orgNodes, people)
  for (const contact of contacts) {
    people.push({
      key: `contact:${contact.id}`,
      kind: 'contact',
      name: contact.full_name,
      subtitle: contact.role_title ?? '',
      channel: contact.email ?? contact.phone ?? null,
      userId: null,
      // Not a hierarchy member — there is no org-chart node to open a drawer on.
      orgNodeId: null,
    })
  }
  return people
}

/**
 * Group people by the company's teams, with the leftovers in one honest bucket.
 *
 * With no teams the caller gets a single ungrouped group, which the view
 * renders flat beside an empty state — never a fabricated group per person.
 * A person in several teams appears under each, which is what the data says.
 */
export function groupPeopleByTeam(people: OrgPerson[], teams: CompanyTeam[]): OrgPeopleGroup[] {
  const claimed = new Set<string>()
  const groups: OrgPeopleGroup[] = []

  for (const team of teams) {
    const members = new Set(team.member_user_ids)
    const inTeam = people.filter((person) => person.userId !== null && members.has(person.userId))
    for (const person of inTeam) claimed.add(person.key)
    groups.push({ id: team.id, name: team.name, people: inTeam })
  }

  const ungrouped = people.filter((person) => !claimed.has(person.key))
  if (ungrouped.length > 0) {
    groups.push({ id: UNGROUPED_TEAM_ID, name: '', people: ungrouped })
  }
  return groups
}

/** How many people of each kind the list holds — the header's honest count. */
export function countByKind(people: OrgPerson[]): Record<PersonKind, number> {
  const counts: Record<PersonKind, number> = { agent: 0, user: 0, contact: 0 }
  for (const person of people) counts[person.kind] += 1
  return counts
}
