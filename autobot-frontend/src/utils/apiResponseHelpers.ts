/**
 * API Response Helper Utilities
 *
 * This module provides reusable utilities for handling API responses
 * across the application, particularly for dealing with ApiClient
 * response inconsistencies.
 *
 * Background:
 * ApiClient base methods (get, post, put, delete) return already-parsed JSON
 * (Promise<T>), NOT Response objects. This module handles legacy call sites that
 * pass either parsed data or a Response object defensively.
 */

/**
 * Safely parse API response
 *
 * Handles both Response objects and pre-parsed JSON data from ApiClient.
 * Uses defensive programming to check if .json() method exists before calling.
 * ApiClient.get<T>()/post<T>() return already-parsed Promise<T> — callers should
 * prefer typed ApiClient calls directly and pass T here for type safety.
 *
 * @param response - API response (either Response object or parsed JSON)
 * @returns Parsed JSON data as T (defaults to unknown)
 *
 * @example
 * ```typescript
 * const data = await parseApiResponse<MyType>(await apiClient.get('/api/endpoint'))
 * ```
 */
export async function parseApiResponse<T = unknown>(response: unknown): Promise<T> {
  // Check if response has .json() method (it's a Response object)
  if (response !== null && typeof response === 'object' && typeof (response as Response).json === 'function') {
    return await (response as Response).json()
  }

  // Already parsed or direct data
  return response as T
}

/**
 * Check if API response indicates success
 *
 * @param data - Parsed response data
 * @returns True if response indicates success
 */
export function isSuccessResponse(data: unknown): boolean {
  return (data as Record<string, unknown>)?.status === 'success'
}

/**
 * Extract error message from API response
 *
 * @param data - Parsed response data
 * @param fallback - Fallback error message
 * @returns Error message string
 */
export function getErrorMessage(data: unknown, fallback = 'Unknown error'): string {
  const record = data as Record<string, unknown> | null
  return (record?.message as string) || (record?.error as string) || fallback
}
