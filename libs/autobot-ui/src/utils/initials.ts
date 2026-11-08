// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * The one rule for a person's initials (#14780 BaseAvatar). Eight views carried three rules
 * between them (split on spaces only, on spaces/_/-, or the first two characters), so the
 * same name showed different initials on different screens.
 *
 * Words are split on whitespace, `.`, `_` and `-`: two or more words give the first letter
 * of the first two; a single word gives its first two letters. Letters are whole code
 * points of the NFC form, so an accented (even decomposed) or non-Latin name is not cut in half.
 */
export function initialsOf(name: string | null | undefined): string {
  const words = (name ?? '').normalize('NFC').split(/[\s._-]+/).filter(Boolean)
  if (words.length === 0) return ''
  const letters =
    words.length > 1 ? [Array.from(words[0])[0], Array.from(words[1])[0]] : Array.from(words[0]).slice(0, 2)
  return letters.join('').toUpperCase()
}
