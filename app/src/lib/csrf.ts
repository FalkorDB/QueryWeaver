/**
 * CSRF protection utilities.
 *
 * The backend sets a `csrf_token` cookie (non-HttpOnly) on every response.
 * State-changing requests (POST, PUT, DELETE, PATCH) must echo the cookie
 * value back via the `X-CSRF-Token` header.
 */

const CSRF_COOKIE_NAME = 'csrf_token';

/**
 * Read the CSRF token from the cookie jar.
 */
export function getCsrfToken(): string {
  if (typeof document === 'undefined') {
    return '';
  }
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${CSRF_COOKIE_NAME}=([^;]*)`)
  );
  if (!match) {
    console.debug(
      `CSRF token cookie "${CSRF_COOKIE_NAME}" not found. ` +
        'State-changing requests may fail with 403 until the cookie is set.'
    );
    return '';
  }
  return decodeURIComponent(match[1]);
}

/**
 * Return headers object containing the CSRF token.
 * Merge this into every state-changing fetch call.
 */
export function csrfHeaders(): Record<string, string> {
  const token = getCsrfToken();
  return token ? { 'X-CSRF-Token': token } : {};
}
