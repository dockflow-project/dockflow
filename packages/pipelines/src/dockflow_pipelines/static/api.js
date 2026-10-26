/** Only same-origin requests; the bearer credential lives exclusively in memory. */
import { el, button, modal, labeled, errorBox, clear } from './dom.js';
let token = '';
let controller = new AbortController();
export const API = '/dockflow/v1';
export const basePath = new URL('../../', import.meta.url).pathname.replace(
  /\/$/,
  '',
);
export function newPage() {
  controller.abort();
  controller = new AbortController();
  return controller.signal;
}
export function signal() {
  return controller.signal;
}
export function hasToken() {
  return Boolean(token);
}
export function forgetToken() {
  token = '';
  newPage();
}
export async function request(path, options = {}) {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\'))
    throw new Error('Only same-origin API paths are allowed');
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', 'Bearer ' + token);
  let body = options.body;
  if (body !== undefined && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(basePath + path, {
      ...options,
      body,
      headers,
      signal: options.signal || controller.signal,
      credentials: 'omit',
      redirect: 'error',
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error(
      'Cannot reach the service. Check the connection and retry. ' +
        (options.method === 'POST'
          ? 'The request may have been accepted; check the result before retrying.'
          : ''),
    );
  }
  let value;
  try {
    value = await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    value = null;
  }
  if (!response.ok) {
    const detail =
      value && typeof value === 'object' ? value.error || value : {};
    const error = Object.assign(
      new Error(
        detail.message ||
          `The service returned HTTP ${response.status} without a JSON error response.`,
      ),
      {
        status: response.status,
        code: detail.code,
        details: detail.details,
        requestId: detail.request_id,
        data: value,
      },
    );
    if (response.status === 401) {
      token = '';
      window.dispatchEvent(new Event('dockflow:unauthorized'));
    }
    throw error;
  }
  if (value === null)
    throw Object.assign(
      new Error('The service returned an invalid JSON response.'),
      { status: response.status, code: 'INVALID_RESPONSE' },
    );
  return value;
}
export function get(path, query = {}) {
  const params = new URLSearchParams(
    Object.entries(query).filter(
      ([, v]) => v !== '' && v !== null && v !== undefined,
    ),
  );
  return request(API + path + (params.size ? '?' + params : ''));
}
export function post(path, body, headers) {
  return request(API + path, { method: 'POST', body, headers });
}
export async function collect(path, query = {}, limit = 2000) {
  const items = [];
  let pageToken;
  do {
    const page = await get(path, {
      ...query,
      page_size: Math.min(200, limit - items.length),
      page_token: pageToken,
    });
    items.push(...page.items);
    pageToken = page.next_page_token;
  } while (pageToken && items.length < limit);
  return { items, truncated: Boolean(pageToken) };
}
export function authenticate(after) {
  const input = el('input', {
    type: 'password',
    autocomplete: 'off',
    required: true,
    placeholder: 'Service bearer token',
  });
  const errors = el('div');
  const submit = el('button', { type: 'submit', class: 'primary' }, 'Connect');
  const form = el(
    'form',
    {},
    el(
      'p',
      {},
      'Enter the token configured for this service. It is kept only in this page’s memory and cleared on reload or sign out.',
    ),
    labeled('Bearer token', input),
    errors,
    el('div', { class: 'actions' }, submit),
  );
  const dialog = modal('Connect to Dockflow', form);
  dialog.dataset.kind = 'authentication';
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    token = input.value.trim();
    try {
      await get('/capabilities');
      input.value = '';
      dialog.close();
      after();
    } catch (error) {
      token = '';
      clear(errors, errorBox(error));
    } finally {
      submit.disabled = false;
    }
  });
  input.focus();
}
