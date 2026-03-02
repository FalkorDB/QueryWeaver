/* eslint-disable @typescript-eslint/no-explicit-any */

import { APIRequestContext, request } from "@playwright/test"

/**
 * Extract the CSRF token from a response's Set-Cookie header.
 * The backend sets a `csrf_token` cookie on every response.
 */
function extractCsrfToken(setCookieHeaders: string[]): string | undefined {
  for (const header of setCookieHeaders) {
    const match = header.match(/csrf_token=([^;]+)/);
    if (match) return match[1];
  }
  return undefined;
}

/**
 * Per-context CSRF token cache.  After the first seed request the token is
 * stored and reused for subsequent calls on the same APIRequestContext,
 * avoiding an extra GET /auth-status on every state-changing request.
 */
const csrfCache = new WeakMap<APIRequestContext, string>();

/**
 * Seed the CSRF cookie on the given request context by making a lightweight
 * GET (only on the first call), then return the cached token value.
 *
 * When the context is initialised from a storageState that already contains
 * a csrf_token cookie, the server will NOT set a new one (no Set-Cookie
 * header).  In that case we fall back to reading the cookie value that is
 * already stored in the context.
 */
async function getCsrfToken(baseUrl: string, ctx: APIRequestContext): Promise<string | undefined> {
  const cached = csrfCache.get(ctx);
  if (cached) return cached;

  const seedResp = await ctx.get(`${baseUrl}/auth-status`);
  const setCookies = seedResp.headersArray()
    .filter(h => h.name.toLowerCase() === 'set-cookie')
    .map(h => h.value);
  let token = extractCsrfToken(setCookies);

  // If the server didn't set a new cookie, the context may already carry one
  // from its storageState – read it directly.
  if (!token) {
    const state = await ctx.storageState();
    const existing = state.cookies.find(c => c.name === 'csrf_token');
    if (existing) token = existing.value;
  }

  if (token) csrfCache.set(ctx, token);
  return token;
}

/**
 * Derive the origin (scheme + host + port) from a full URL so we can call
 * `getCsrfToken` without requiring callers to pass the base URL separately.
 */
function originOf(url: string): string {
  const u = new URL(url);
  return u.origin;
}

const getRequest = async (url: string, headers?: Record<string, string>, body?: any, availableRequest?: APIRequestContext) => {
  const requestOptions = {
    data: body,
    headers: headers || undefined,
  };

  const requestContext = availableRequest || (await request.newContext());
  const response = await requestContext.get(url, requestOptions);
  return response;
};

const postRequest = async (url: string, body?: any, availableRequest?: APIRequestContext, headers?: Record<string, string>) => {
  const requestContext = availableRequest || (await request.newContext());
  const csrfToken = await getCsrfToken(originOf(url), requestContext);

  const requestOptions = {
    data: body,
    headers: {
      ...(headers || {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
  };

  const response = await requestContext.post(url, requestOptions);
  return response;
};

const deleteRequest = async (url: string, headers?: Record<string, string>, body?: any, availableRequest?: APIRequestContext) => {
  const requestContext = availableRequest || (await request.newContext());
  const csrfToken = await getCsrfToken(originOf(url), requestContext);

  const requestOptions = {
    data: body,
    headers: {
      ...(headers || {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
  };

  const response = await requestContext.delete(url, requestOptions);
  return response;
};

const patchRequest = async (url: string, body?: any, availableRequest?: APIRequestContext, headers?: Record<string, string>) => {
  const requestContext = availableRequest || (await request.newContext());
  const csrfToken = await getCsrfToken(originOf(url), requestContext);

  const requestOptions = {
    data: body,
    headers: {
      ...(headers || {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
  };

  const response = await requestContext.patch(url, requestOptions);
  return response;
};

export { getRequest, deleteRequest, postRequest, patchRequest }