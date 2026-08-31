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
 * queried by `get_org_chart`. That holds by construction rather than by test:
 * `LLCContact` is referenced outside tests only in `llc/models/contact.py`,
 * `llc/models/__init__.py`, `llc/services/contact.py` and `llc/services/company.py`
 * — never in `llc/api/companies.py` — and `is_human` has exactly two construction
 * sites there (`True` for a membership, `False` for an `AgentOrgNode`). Two
 * branches over disjoint tables, so provenance is a total function on the three
 * kinds and no row can be claimed twice.
 *
 * (An earlier version of this comment cited `llc/tests/test_contact_no_login.py`
 * as the guard. That path does not exist — the real file is
 * `test_contacts_no_login.py`, and it pins the *authentication* boundary: no auth
 * columns, no FK to `users`, no contact email resolving through user lookup. It
 * says nothing about `get_org_chart`.)
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
  /**
   * Whether this person can still be given work (#13956). Absent for agents,
   * and absent from a server that predates the field — which is why every
   * reader tests `=== false` rather than falsiness.
   */
  is_active?: boolean | null
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
  /**
   * Deactivated or soft-deleted, and so no longer assignable (#13956).
   *
   * Shown rather than filtered out: their work items stay behind when they
   * leave, and so does the role they held, so a chart that omits them cannot
   * explain who those items belong to.
   */
  isInactive: boolean
  /**
   * Raw contact channels, kept separate from the merged display-only
   * `channel` above (#14603) — editing needs email and phone as two
   * independent fields, not whichever one `channel` picked to show. `null`
   * for `agent`/`user`, which have no contact record behind them.
   */
  contactEmail: string | null
  contactPhone: string | null
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

/**
 * `contact:<id>` — the one place this prefix is spelled out (#14603). Both
 * `buildOrgPeople` (below) and the People list's inline editor need it, and a
 * second literal `'contact:'` is how the two drift.
 */
const CONTACT_KEY_PREFIX = 'contact:'

/** The `llc_contacts` id inside a `contact:<id>` person key. */
export function contactIdOfKey(key: string): string {
  return key.startsWith(CONTACT_KEY_PREFIX) ? key.slice(CONTACT_KEY_PREFIX.length) : key
}

/** The editable fields `PATCH /api/llc/contacts/{company_id}/{contact_id}` accepts (#14603). */
export interface ContactEditPatch {
  full_name: string
  role_title: string
  email: string
  phone: string
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
      // `=== false` and not falsiness: agents omit the field entirely, and so
      // does a server that predates it. Treating absent as inactive would mark
      // every agent and every person during a rolling update.
      isInactive: node.is_active === false,
      // Not a contact — no raw channel data exists to carry.
      contactEmail: null,
      contactPhone: null,
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
      key: `${CONTACT_KEY_PREFIX}${contact.id}`,
      kind: 'contact',
      name: contact.full_name,
      subtitle: contact.role_title ?? '',
      channel: contact.email ?? contact.phone ?? null,
      userId: null,
      // Not a hierarchy member — there is no org-chart node to open a drawer on.
      orgNodeId: null,
      // A contact has no account, so there is no account to deactivate.
      isInactive: false,
      contactEmail: contact.email ?? null,
      contactPhone: contact.phone ?? null,
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
