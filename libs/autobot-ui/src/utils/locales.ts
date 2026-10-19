// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Language names for a language picker (#18354).
 *
 * Each language is named in ITS OWN language (an endonym), not translated: a
 * user who has landed in a language they cannot read must still find theirs
 * in the list, and "Deutsch" is the right label for German in every locale.
 * The one place a UI literal is the correct answer, so it lives once, here.
 */

/** Endonyms for the locales both apps ship. */
export const LOCALE_ENDONYMS: Readonly<Record<string, string>> = {
  ar: 'العربية',
  de: 'Deutsch',
  en: 'English',
  es: 'Español',
  fa: 'فارسی',
  fr: 'Français',
  he: 'עברית',
  lv: 'Latviešu',
  pl: 'Polski',
  pt: 'Português',
  ur: 'اردو',
}

export interface LocaleOption {
  code: string
  label: string
}

/** Options for the given locale codes, each labelled by its endonym (the code if unknown). */
export function localeOptions(codes: readonly string[]): LocaleOption[] {
  return codes.map((code) => ({ code, label: LOCALE_ENDONYMS[code] ?? code }))
}
