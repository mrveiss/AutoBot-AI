/**
 * fetchWithAuth — drop-in replacement for fetch() that injects the JWT
 * Authorization header from localStorage.
 *
 * Reads the same key as ApiClient._getAuthToken() so auth state is consistent.
 * Use this for any raw fetch() call that needs to reach an authenticated backend
 * endpoint.  ApiClient.rawRequest() is preferred for new code; this helper
 * exists to fix existing raw fetch() call-sites without a full refactor.
 *
 * Issue #979: JWT token not attached to backend API requests.
 */

export function getAuthToken(): string | null {
  try {
    const stored = localStorage.getItem('autobot_auth')
    if (!stored) return null
    const auth: { token?: string } = JSON.parse(stored)
    if (auth.token && auth.token !== 'single_user_mode') {
      return auth.token
    }
    return null
  } catch {
    return null
  }
}

/**
 * Wraps native fetch() with Bearer-token injection.
 * If no valid token is found, the request proceeds unauthenticated
 * (matches pre-existing behaviour; let the server decide).
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAuthToken()
  if (!token) {
    return fetch(url, options)
  }

  // Build a new Headers object so we don't mutate the caller's options.
  const headers = new Headers(options.headers)
  if (!headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(url, { ...options, headers })
}
