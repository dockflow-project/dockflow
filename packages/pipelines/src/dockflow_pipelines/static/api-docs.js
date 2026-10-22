/** Packaged, read-only explorer of the service's actual OpenAPI document. */
import {
  API,
  request,
  newPage,
  authenticate,
  hasToken,
  forgetToken,
} from './api.js';
import {
  el,
  button,
  clear,
  json,
  notice,
  errorBox,
  section,
  pageHeader,
  labeled,
  download,
} from './dom.js';

const content = document.getElementById('content');
const connect = document.getElementById('connect');
const methods = new Set([
  'get',
  'post',
  'put',
  'patch',
  'delete',
  'head',
  'options',
  'trace',
]);
let generation = 0;

function updateConnection() {
  connect.textContent = hasToken() ? 'Sign out' : 'Connect';
  connect.onclick = () => {
    if (hasToken()) {
      generation += 1;
      forgetToken();
      clear(
        content,
        notice('Signed out. Connect to view the API reference.'),
        button('Connect', signIn, 'primary'),
      );
      updateConnection();
    } else signIn();
  };
}

function signIn() {
  if (!document.getElementById('modal').open) authenticate(load);
}

function schemaDetails(title, value, open = false) {
  return el('details', { open }, el('summary', {}, title), json(value));
}

function operationDetails(path, method, operation, inherited) {
  const parameters = new Map();
  for (const parameter of [
    ...(inherited || []),
    ...(operation.parameters || []),
  ]) {
    parameters.set(
      parameter.$ref || `${parameter.in}:${parameter.name}`,
      parameter,
    );
  }
  const responses = Object.entries(operation.responses || {});
  const body = el(
    'div',
    {},
    operation.description ? el('p', {}, operation.description) : null,
    operation.operationId
      ? el(
          'p',
          { class: 'subtle' },
          'Operation ID: ',
          el('code', {}, operation.operationId),
        )
      : null,
    operation.deprecated
      ? notice('This operation is marked deprecated by the service.')
      : null,
    operation.tags?.length
      ? el('p', { class: 'subtle' }, 'Tags: ' + operation.tags.join(', '))
      : null,
    parameters.size
      ? section(
          'Parameters',
          [...parameters.values()].map((parameter) =>
            schemaDetails(
              parameter.$ref ||
                `${parameter.name} · ${parameter.in}${parameter.required ? ' · required' : ''}`,
              parameter,
            ),
          ),
        )
      : null,
    operation.requestBody
      ? section('Request body', json(operation.requestBody))
      : null,
    section(
      'Responses',
      responses.length
        ? responses.map(([status, response]) =>
            schemaDetails(
              `${status}${response.description ? ' · ' + response.description : ''}`,
              response,
            ),
          )
        : el('p', { class: 'subtle' }, 'No response schema is declared.'),
    ),
    operation.security !== undefined
      ? schemaDetails('Operation authentication', operation.security)
      : null,
    schemaDetails('Complete operation schema', operation),
  );
  return el(
    'details',
    { class: 'api-operation' },
    el(
      'summary',
      {},
      el('span', { class: 'http-method ' + method }, method.toUpperCase()),
      el('code', {}, path),
      operation.summary ? el('span', {}, operation.summary) : null,
    ),
    body,
  );
}

function render(schema) {
  const operations = [];
  for (const [path, pathItem] of Object.entries(schema.paths)) {
    for (const [method, operation] of Object.entries(pathItem)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object')
        continue;
      operations.push({
        path,
        method,
        operation,
        inherited: pathItem.parameters,
        search:
          `${method} ${path} ${operation.summary || ''} ${operation.description || ''} ${operation.operationId || ''} ${(operation.tags || []).join(' ')}`.toLowerCase(),
      });
    }
  }
  const schemas = Object.entries(schema.components?.schemas || {});
  const search = el('input', {
    type: 'search',
    placeholder: 'Path, operation or schema name',
    autocomplete: 'off',
  });
  const method = el(
    'select',
    {},
    el('option', { value: '' }, 'All methods'),
    [...new Set(operations.map((item) => item.method))]
      .sort()
      .map((value) => el('option', { value }, value.toUpperCase())),
  );
  const results = el('div');
  const count = el('p', {
    class: 'subtle',
    role: 'status',
    'aria-live': 'polite',
  });
  const componentResults = el('div');
  function filter() {
    const words = search.value
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    const selected = operations.filter(
      (item) =>
        (!method.value || item.method === method.value) &&
        words.every((word) => item.search.includes(word)),
    );
    const selectedSchemas = schemas.filter(([name, value]) =>
      words.every((word) =>
        `${name} ${JSON.stringify(value)}`.toLowerCase().includes(word),
      ),
    );
    count.textContent = `${selected.length} of ${operations.length} operations · ${selectedSchemas.length} of ${schemas.length} component schemas`;
    clear(
      results,
      selected.length
        ? el(
            'div',
            { class: 'panel flush' },
            selected.map((item) =>
              operationDetails(
                item.path,
                item.method,
                item.operation,
                item.inherited,
              ),
            ),
          )
        : notice('No operations match these filters.'),
    );
    clear(
      componentResults,
      selectedSchemas.length
        ? section(
            'Component schemas',
            selectedSchemas.map(([name, value]) => schemaDetails(name, value)),
          )
        : notice('No component schemas match this search.'),
    );
  }
  search.addEventListener('input', filter);
  method.addEventListener('change', filter);
  clear(
    content,
    pageHeader(
      schema.info?.title || 'Dockflow API reference',
      `Version ${schema.info?.version || 'unspecified'} · OpenAPI ${schema.openapi || 'unspecified'}`,
      [
        button('Refresh', load),
        button('Download OpenAPI', () =>
          download(
            'dockflow-openapi.json',
            JSON.stringify(schema, null, 2) + '\n',
          ),
        ),
      ],
    ),
    schema.info?.description ? el('p', {}, schema.info.description) : null,
    el(
      'p',
      { class: 'subtle' },
      'Browse request and response contracts from this service. Schema references resolve to the component definitions below.',
    ),
    el(
      'div',
      { class: 'toolbar' },
      labeled('Search operations and schemas', search),
      labeled('HTTP method', method),
    ),
    count,
    results,
    componentResults,
    schema.components?.securitySchemes
      ? section(
          'Authentication schemes',
          json(schema.components.securitySchemes),
          schema.security
            ? schemaDetails(
                'Default authentication requirements',
                schema.security,
              )
            : null,
        )
      : null,
  );
  filter();
}

async function load() {
  const current = ++generation;
  newPage();
  clear(
    content,
    el(
      'div',
      { class: 'loading', role: 'status' },
      'Loading the live OpenAPI contract…',
    ),
  );
  try {
    const schema = await request(API + '/openapi.json');
    if (current !== generation) return;
    if (
      !schema ||
      !schema.paths ||
      typeof schema.paths !== 'object' ||
      Array.isArray(schema.paths)
    )
      throw new Error('The service returned an invalid OpenAPI document.');
    render(schema);
  } catch (error) {
    if (current !== generation || error.name === 'AbortError') return;
    clear(
      content,
      pageHeader('API reference', 'The live API contract could not be loaded.'),
      errorBox(error, error.status === 401 ? signIn : load),
    );
    if (error.status === 401) signIn();
  } finally {
    if (current === generation) updateConnection();
  }
}

window.addEventListener('dockflow:unauthorized', () => {
  updateConnection();
  signIn();
});
updateConnection();
load();
