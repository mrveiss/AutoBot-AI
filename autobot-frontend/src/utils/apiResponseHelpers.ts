/**
 * API Response Helper Utilities
 *
 * This module provides reusable utilities for handling API responses
 * across the application, particularly for dealing with ApiClient
 * response inconsistencies.
 *
 * Background:
 * ApiClient has dual behavior:
 * - Base methods (get, post, put, delete) return Response objects
 * - Helper methods return parsed JSON directly
 *
 * These utilities provide defensive handling for both cases.
 */

/**
 * Safely parse API response
 *
 * Handles both Response objects and pre-parsed JSON data from ApiClient.
 * Uses defensive programming to check if .json() method exists before calling.
 *
 * @param response - API response (either Response object or parsed JSON)
 * @returns Parsed JSON data
 *
 * @example
 * ```typescript
 * const response = await apiClient.get('/api/endpoint')
 * const data = await parseApiResponse(response)
 * ```
 */
export async function parseApiResponse(response: Response | Record<string, unknown>): Promise<unknown> {
  // Check if response has .json() method (it's a Response object)
  if (typeof (response as Response).json === 'function') {
    return await (response as Response).json()
  }

  // Already parsed or direct data
  return response
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
