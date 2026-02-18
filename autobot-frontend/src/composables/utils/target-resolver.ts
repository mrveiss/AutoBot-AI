import { isRef, unref, type Ref } from 'vue'

/**
 * Resolve target to actual DOM element/Document/Window
 *
 * Handles both direct element references and Vue refs.
 * Falls back to document if ref is null/undefined.
 *
 * @param target - Element, Document, Window, or Ref to any of these
 * @returns Resolved target (never null)
 *
 * @example
 * ```typescript
 * const divRef = ref<HTMLElement>()
 * const actualDiv = resolveTarget(divRef)  // Returns element or document
 *
 * const directDiv = document.querySelector('.my-div')
 * const sameDiv = resolveTarget(directDiv)  // Returns element as-is
 * ```
 */
export function resolveTarget(
  target: HTMLElement | Document | Window | Ref<HTMLElement | undefined | null>
): HTMLElement | Document | Window {
  if (isRef(target)) {
    return unref(target) || document
  }
  return target
}
