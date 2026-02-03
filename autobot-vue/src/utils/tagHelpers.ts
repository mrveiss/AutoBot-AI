/**
 * Tag Helpers
 *
 * Utility functions for parsing and processing tags across the application.
 * Ensures consistent tag handling in knowledge base, document management, and other features.
 */

/**
 * Parse comma-separated tags string into array of trimmed, non-empty tags
 *
 * @param tagsInput - Comma-separated string of tags (e.g., "tag1, tag2, tag3")
 * @returns Array of trimmed, non-empty tag strings
 *
 * @example
 * parseTags("javascript, vue, typescript")
 * // Returns: ["javascript", "vue", "typescript"]
 *
 * parseTags(" tag1 ,  tag2  , , tag3 ")
 * // Returns: ["tag1", "tag2", "tag3"]
 */
export function parseTags(tagsInput: string): string[] {
  if (!tagsInput || typeof tagsInput !== 'string') {
    return []
  }

  return tagsInput
    .split(',')
    .map(tag => tag.trim())
    .filter(tag => tag.length > 0)
}

/**
 * Convert tag array back to comma-separated string
 *
 * @param tags - Array of tag strings
 * @returns Comma-separated string
 *
 * @example
 * tagsToString(["javascript", "vue", "typescript"])
 * // Returns: "javascript, vue, typescript"
 */
export function tagsToString(tags: string[]): string {
  if (!Array.isArray(tags)) {
    return ''
  }

  return tags
    .filter(tag => tag && tag.trim().length > 0)
    .join(', ')
}

/**
 * Validate tag format (alphanumeric, hyphens, underscores only)
 *
 * @param tag - Single tag to validate
 * @returns True if valid, false otherwise
 *
 * @example
 * isValidTag("my-tag")      // true
 * isValidTag("my_tag_123")  // true
 * isValidTag("my tag!")     // false
 */
export function isValidTag(tag: string): boolean {
  if (!tag || typeof tag !== 'string') {
    return false
  }

  // Allow alphanumeric characters, hyphens, underscores, and spaces
  // Tag must be between 1-50 characters
  const tagRegex = /^[a-zA-Z0-9\s\-_]{1,50}$/
  return tagRegex.test(tag.trim())
}

/**
 * Sanitize and validate tags, removing invalid ones
 *
 * @param tags - Array of tags to sanitize
 * @param maxTags - Maximum number of tags allowed (default: 20)
 * @returns Array of valid, sanitized tags
 *
 * @example
 * sanitizeTags(["valid", "my-tag", "invalid!", "  spaces  "])
 * // Returns: ["valid", "my-tag", "spaces"]
 */
export function sanitizeTags(tags: string[], maxTags: number = 20): string[] {
  if (!Array.isArray(tags)) {
    return []
  }

  return tags
    .map(tag => tag.trim())
    .filter(tag => tag.length > 0 && isValidTag(tag))
    .filter((tag, index, self) => self.indexOf(tag) === index) // Remove duplicates
    .slice(0, maxTags) // Limit to maxTags
}

/**
 * Parse and sanitize tags from input string
 *
 * @param tagsInput - Comma-separated string of tags
 * @param maxTags - Maximum number of tags allowed (default: 20)
 * @returns Array of valid, sanitized tags
 *
 * @example
 * parseAndSanitizeTags("valid, my-tag, invalid!, duplicate, duplicate")
 * // Returns: ["valid", "my-tag", "duplicate"]
 */
export function parseAndSanitizeTags(tagsInput: string, maxTags: number = 20): string[] {
  const parsed = parseTags(tagsInput)
  return sanitizeTags(parsed, maxTags)
}
