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
 * Seed the CSRF cookie on the given request context by making a lightweight
 * GET, then return the token value so callers can include it as a header.
 */
async function getCsrfToken(baseUrl: string, ctx: APIRequestContext): Promise<string | undefined> {
  const seedResp = await ctx.get(`${baseUrl}/auth-status`);
  const setCookies = seedResp.headersArray()
    .filter(h => h.name.toLowerCase() === 'set-cookie')
    .map(h => h.value);
  return extractCsrfToken(setCookies);
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