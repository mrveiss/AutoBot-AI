// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Client-side mirror of the contact validation the API enforces (#14105).
 *
 * #14105 asks for "the same validation the API enforces … surfaced as field
 * errors rather than a raw 422". Before this, only the `full_name` non-blank
 * rule existed here, so a mistyped phone number travelled to the server and
 * came back as a 422 the user could not attribute to a field.
 *
 * The bounds below are transcribed from `autobot-backend/llc/api/contacts.py`
 * (`ContactCreate` / `ContactUpdate`) and deliberately named after it, so the
 * next person reading either side can see they are meant to agree. They are a
 * *mirror*, not the enforcement: the API is still the authority, and a payload
 * that gets past this must still be rejected there. The point is to tell the
 * user which field is wrong before a round trip, not to move the gate.
 */

/** `_PHONE_PATTERN` in llc/api/contacts.py. */
export const PHONE_PATTERN = /^\+?[0-9()\-.\s]{3,64}$/

/** Field length bounds, matching the `Field(max_length=…)` declarations. */
export const FULL_NAME_MAX = 255
export const EMAIL_MAX = 320
export const PHONE_MAX = 64
export const ROLE_TITLE_MAX = 255
/** `_NOTES_MAX_LENGTH`. No notes input exists in this surface yet; declared so
 *  the mirror is complete if one is added. */
export const NOTES_MAX = 2000

export interface ContactDraft {
  full_name: string
  role_title: string
  email: string
  phone: string
  notes?: string
}

/** i18n key per invalid field, or an empty object when the draft is valid. */
export type ContactFieldErrors = Partial<Record<keyof ContactDraft, string>>

export function validateContact(draft: ContactDraft): ContactFieldErrors {
  const errors: ContactFieldErrors = {}

  const fullName = draft.full_name.trim()
  if (!fullName) {
    errors.full_name = 'llc.orgPeople.validation.fullNameRequired'
  } else if (fullName.length > FULL_NAME_MAX) {
    errors.full_name = 'llc.orgPeople.validation.fullNameTooLong'
  }

  const email = draft.email.trim()
  if (email && email.length > EMAIL_MAX) {
    errors.email = 'llc.orgPeople.validation.emailTooLong'
  }

  const phone = draft.phone.trim()
  if (phone) {
    // Length first: an over-long value also fails the pattern, and "too long"
    // is the more actionable of the two messages.
    if (phone.length > PHONE_MAX) {
      errors.phone = 'llc.orgPeople.validation.phoneTooLong'
    } else if (!PHONE_PATTERN.test(phone)) {
      errors.phone = 'llc.orgPeople.validation.phoneInvalid'
    }
  }

  if (draft.role_title.trim().length > ROLE_TITLE_MAX) {
    errors.role_title = 'llc.orgPeople.validation.roleTitleTooLong'
  }

  if ((draft.notes ?? '').length > NOTES_MAX) {
    errors.notes = 'llc.orgPeople.validation.notesTooLong'
  }

  return errors
}

export function isValidContact(draft: ContactDraft): boolean {
  return Object.keys(validateContact(draft)).length === 0
}
