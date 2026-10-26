/** Read views for the catalog, execution history and artifact provenance. */
import {
  el,
  clear,
  button,
  link,
  json,
  short,
  date,
  duration,
  badge,
  empty,
  notice,
  errorBox,
  table,
  fields,
  tabs,
  section,
  pageHeader,
  download,
  labeled,
  toast,
  listScreen,
  localList,
  referenceLabel,
} from './dom.js';
import { get, post, collect, request } from './api.js';
import { graph, graphModel, graphQueryKey } from './graph.js';
import { plainLogEntries } from './logs.js';
import { deleteResource } from './cleanup.js';
import { artifactContents } from './contents.js';
import { autocomplete, filterValue } from './autocomplete.js';
import {
  uploadPipeline,
  createExperiment,
  createArtifact,
  uploadArtifact,
  confirmAction,
} from './forms.js';

function graphSettings(query, route, navigate, readQuery = () => query) {
  return {
    path: query.has('graph') ? query.get('graph') : undefined,
    all: query.get('graph-view') === 'all',
    onNavigate: ({ path, all }) => {
      const next = new URLSearchParams(readQuery());
      next.set('graph', path);
      if (all) next.set('graph-view', 'all');
      else next.delete('graph-view');
      next.delete('node');
      navigate(route, next);
    },
  };
}

function detailLayout(container, body, tab) {
  body.classList.add('detail-body');
  body.classList.toggle('graph-body', tab === 'Graph');
  const information = tab !== 'Graph';
  if (information && !body.classList.contains('list-body')) {
    body.setAttribute('role', 'region');
    body.setAttribute('tabindex', '0');
    body.setAttribute('aria-label', (tab || 'Element') + ' information');
  }
  const context = [...container.childNodes].filter((node) => node !== body);
  const tabBar = context.find((node) => node.classList?.contains('tabs'));
  const header = el(
    'header',
    { class: 'detail-header' },
    information
      ? [
          el(
            'div',
            { class: 'detail-context' },
            context.filter((node) => node !== tabBar),
          ),
          tabBar,
        ]
      : context,
  );
  const screen = el(
    'section',
    { class: 'detail-screen' + (information ? ' information-screen' : '') },
    header,
    body,
  );
  clear(container, screen);
  return screen;
}

function resourceHeading(
  back,
  path,
  title,
  actions,
  status = null,
  description = '',
) {
  return el(
    'div',
    { class: 'detail-heading' },
    el(
      'div',
      { class: 'detail-title' },
      link(back, path, { class: 'detail-back' }),
      el('span', { class: 'subtle', 'aria-hidden': 'true' }, '/'),
      el('h1', { title: description || title }, title),
      status,
    ),
    el('div', { class: 'actions detail-actions' }, actions),
  );
}

function graphWorkspace(
  body,
  route,
  query,
  navigate,
  graphNode,
  renderPanel,
  onQuery,
) {
  const key = graphQueryKey(query);
  const layout = el('div', { class: 'graph-layout' }, graphNode);
  body.append(layout);
  function updateQuery(next) {
    const viewport = graphNode.captureViewport?.();
    const previous = query.get('node');
    const oldPanel = layout.querySelector('.graph-inspector');
    const inspectorFocused = oldPanel?.contains(document.activeElement);
    query = next;
    onQuery(next);
    const selected = next.get('node');
    graphNode.selectNode?.(selected);
    oldPanel?.remove();
    const panel = selected ? renderPanel(selected, next) : null;
    layout.classList.toggle('has-inspector', Boolean(panel));
    if (!panel) {
      graphNode.restoreViewport?.(viewport);
      if (inspectorFocused)
        [...graphNode.querySelectorAll('.graph-node')]
          .find((node) => node.dataset.node === previous)
          ?.querySelector('.graph-node-select')
          .focus({ preventScroll: true });
      return;
    }
    panel.classList.add('graph-inspector', 'step-panel');
    panel.setAttribute('aria-label', 'Selected step details');
    panel.setAttribute('tabindex', '0');
    const title = panel.querySelector('h2');
    panel.prepend(
      el(
        'div',
        { class: 'inspector-heading' },
        title,
        button(
          '×',
          () => {
            const cleared = new URLSearchParams(query);
            cleared.delete('node');
            cleared.delete('stepTab');
            navigate(route, cleared);
          },
          'icon-button',
          { 'aria-label': 'Close step details' },
        ),
      ),
    );
    layout.append(panel);
    graphNode.restoreViewport?.(viewport);
    if (inspectorFocused)
      panel
        .querySelector('[role="tab"][aria-selected="true"]')
        ?.focus({ preventScroll: true });
  }
  updateQuery(query);
  return {
    path: route,
    accepts: (path, next) => path === route && graphQueryKey(next) === key,
    updateQuery,
  };
}

const RUN_STATES = [
  'queued',
  'running',
  'cancelling',
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
];
export const terminal = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
]);
function nameCell(name, id, path) {
  return el(
    'div',
    {},
    link(name || short(id), path, { class: 'cell-main' }),
    el('span', { class: 'cell-detail id' }, short(id)),
  );
}
function artifactLinks(values = {}) {
  return Object.keys(values).length
    ? el(
        'div',
        { class: 'artifact-links' },
        Object.entries(values).map(([name, id]) =>
          el(
            'div',
            {},
            el('span', { class: 'subtle' }, name + ' · '),
            link(short(id), 'artifacts/' + id),
          ),
        ),
      )
    : el('span', { class: 'subtle' }, 'No artifacts');
}
export function runRows(runs, select) {
  return runs.map((run) => [
    ...(select ? [select(run)] : []),
    nameCell(run.display_name, run.run_id, 'runs/' + run.run_id),
    badge(run.state),
    date(run.created_at),
    duration(run),
    link(short(run.experiment_id), 'experiments/' + run.experiment_id),
    link(short(run.definition_id), 'definitions/' + run.definition_id),
  ]);
}
function pageHistory(state, route, query) {
  const filters = [...query]
    .filter(([key]) => key !== 'page_token')
    .sort(([a], [b]) => a.localeCompare(b));
  const key = route + '?' + JSON.stringify(filters);
  return (state.pages[key] ||= new Map());
}
function pager(page, query, navigate, route, stack) {
  return el(
    'div',
    { class: 'pager' },
    el(
      'span',
      {},
      `${page.items.length} records on this page${page.next_page_token ? ' · more available' : ''}`,
    ),
    el(
      'div',
      { class: 'actions' },
      button(
        query.get('page_token') && !stack.has(query.get('page_token'))
          ? 'First page'
          : 'Previous',
        () => {
          const next = new URLSearchParams(query);
          next.delete('page_token');
          const previous = stack.get(query.get('page_token'));
          if (previous) next.set('page_token', previous);
          navigate(route, next);
        },
        'secondary',
        { disabled: !query.get('page_token') },
      ),
      button(
        'Next',
        () => {
          stack.set(page.next_page_token, query.get('page_token') || '');
          const next = new URLSearchParams(query);
          next.set('page_token', page.next_page_token);
          navigate(route, next);
        },
        'secondary',
        { disabled: !page.next_page_token },
      ),
    ),
  );
}
function filterForm(query, specs, navigate, route) {
  const controls = specs.map(([key, label, options]) => ({
    key,
    control: options
      ? el(
          'select',
          {},
          el('option', { value: '' }, 'All'),
          options.map((value) => el('option', { value }, value)),
        )
      : el('input', {
          type: 'text',
          placeholder: key === 'type' ? 'Search types' : 'Search by name or ID',
        }),
  }));
  controls.forEach((item) => (item.control.value = query.get(item.key) || ''));
  const related = {
    definition_id: 'definitions',
    experiment_id: 'experiments',
    run_id: 'runs',
    task_id: 'tasks',
  };
  const collection = route.startsWith('experiments/')
    ? 'runs'
    : route === 'executions'
      ? 'attempts'
      : route;
  const controlFor = (key) =>
    controls.find((item) => item.key === key)?.control;
  const valueFor = (key) => {
    const value = controlFor(key) ? filterValue(controlFor(key)) : '';
    return /^(definition|experiment|run|task)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      value,
    )
      ? value
      : '';
  };
  const experiment = () =>
    route.startsWith('experiments/')
      ? route.split('/')[1]
      : valueFor('experiment_id');
  function scopeFor(key) {
    if (collection === 'components' && key === 'search')
      return { definition_id: valueFor('definition_id') };
    if (collection === 'runs') {
      if (key === 'definition_id') return { experiment_id: experiment() };
      if (key === 'search')
        return {
          experiment_id: experiment(),
          definition_id: valueFor('definition_id'),
        };
    }
    if (collection === 'attempts') {
      if (key === 'task_id') return { run_id: valueFor('run_id') };
      if (key === 'search')
        return { run_id: valueFor('run_id'), task_id: valueFor('task_id') };
    }
    return {};
  }
  const dependencies =
    collection === 'components'
      ? { definition_id: ['search'] }
      : collection === 'runs'
        ? {
            experiment_id: ['definition_id', 'search'],
            definition_id: ['search'],
          }
        : collection === 'attempts'
          ? { run_id: ['task_id', 'search'], task_id: ['search'] }
          : {};
  const form = el(
    'form',
    { class: 'toolbar' },
    controls.map((item, i) => {
      const field = labeled(specs[i][1], item.control);
      if (item.control.tagName === 'INPUT')
        field.append(
          autocomplete(
            item.control,
            related[item.key] || collection,
            item.key === 'type' ? 'type' : null,
            () => scopeFor(item.key),
          ),
        );
      return field;
    }),
    el('button', { type: 'submit' }, 'Apply filters'),
    button('Clear', () => navigate(route)),
  );
  for (const [parent, children] of Object.entries(dependencies))
    for (const event of ['input', 'change'])
      controlFor(parent)?.addEventListener(event, () => {
        for (const child of children)
          controlFor(child)?.autocompleteControl?.clear();
      });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const next = new URLSearchParams();
    controls.forEach(({ key, control }) => {
      const value = filterValue(control);
      if (value) next.set(key, value);
    });
    navigate(route, next);
  });
  return form;
}
export async function collection(container, kind, query, navigate, state) {
  const configs = {
    pipelines: {
      title: 'Pipelines',
      subtitle: 'Versioned definitions, ready to run on Docker.',
      filters: [['search', 'Search']],
      headers: ['Name', 'Description', 'Origin', 'Default version', 'Created'],
      row: (p) => [
        nameCell(p.name, p.pipeline_id, 'pipelines/' + p.pipeline_id),
        p.description || '—',
        p.registration_origin || 'configuration',
        link(
          short(p.default_version_id),
          'definitions/' + p.default_version_id,
        ),
        date(p.created_at),
      ],
      action: () =>
        uploadPipeline(null, (p) => navigate('pipelines/' + p.pipeline_id)),
      actionLabel: 'Upload pipeline',
    },
    experiments: {
      title: 'Experiments',
      subtitle: 'Organize and compare related pipeline runs.',
      filters: [['search', 'Search']],
      headers: ['Name', 'Description', 'Created', 'Latest run'],
      row: (e) => [
        nameCell(
          e.display_name,
          e.experiment_id,
          'experiments/' + e.experiment_id,
        ),
        e.description || '—',
        date(e.created_at),
        date(e.last_run_created_at),
      ],
      action: () =>
        createExperiment((e) => navigate('experiments/' + e.experiment_id)),
      actionLabel: 'Create experiment',
    },
    artifacts: {
      title: 'Artifacts',
      subtitle: 'Datasets, models and outputs with durable provenance.',
      filters: [
        ['search', 'Search'],
        ['type', 'Type'],
        [
          'availability',
          'Availability',
          [
            'available',
            'missing',
            'inaccessible',
            'corrupt',
            'deleted',
            'unknown',
          ],
        ],
      ],
      headers: [
        'Artifact',
        'Type',
        'Origin',
        'Availability',
        'Publication',
        'Pinned',
        'Created',
      ],
      row: (a) => [
        nameCell(
          a.version || a.upload?.filename || short(a.artifact_id),
          a.artifact_id,
          'artifacts/' + a.artifact_id,
        ),
        a.type?.schema_title,
        a.creation_origin === 'manual' || !a.producer || a.origin === 'external'
          ? 'Manually added · explicit deletion only'
          : a.origin,
        badge(a.availability),
        badge(a.publication_state),
        a.pinned ? 'Yes' : 'No',
        date(a.created_at),
      ],
      action: () =>
        uploadArtifact((a) => navigate('artifacts/' + a.artifact_id)),
      actionLabel: 'Upload artifact',
      additionalActions: [
        button('Register artifact', () =>
          createArtifact((a) => navigate('artifacts/' + a.artifact_id)),
        ),
      ],
    },
    components: {
      title: 'Components',
      subtitle: 'Immutable component contracts and execution images.',
      filters: [
        ['definition_id', 'Pipeline ID'],
        ['search', 'Component ID'],
      ],
      headers: ['Name', 'Pipeline ID', 'Executor image', 'Created'],
      row: (c) => [
        nameCell(c.name, c.component_id, 'components/' + c.component_id),
        link(short(c.definition_id), 'definitions/' + c.definition_id),
        c.executor?.container?.image || 'Graph / importer',
        date(c.created_at),
      ],
    },
    attempts: {
      title: 'Executions',
      subtitle:
        'Actual attempts, including retries. Reused tasks link to their original attempt.',
      filters: [
        ['search', 'Search'],
        ['run_id', 'Run ID'],
        ['task_id', 'Task ID'],
        [
          'state',
          'State',
          [
            'running',
            'publishing',
            'succeeded',
            'failed',
            'cancelled',
            'interrupted',
          ],
        ],
      ],
      headers: [
        'Attempt',
        'State',
        'Run',
        'Task',
        'Started',
        'Duration',
        'Exit',
      ],
      row: (a) => [
        link(short(a.attempt_id), 'attempts/' + a.attempt_id),
        badge(a.state),
        link(short(a.run_id), 'runs/' + a.run_id),
        link(short(a.task_id), 'tasks/' + a.task_id),
        date(a.started_at),
        duration(a),
        a.exit_status ?? '—',
      ],
    },
  };
  if (kind === 'runs') return runsList(container, query, navigate, state);
  const config = configs[kind],
    page = await get('/' + kind, Object.fromEntries(query));
  const route = kind === 'attempts' ? 'executions' : kind;
  const stack = pageHistory(state, route, query);
  clear(
    container,
    listScreen(
      [
        pageHeader(config.title, config.subtitle, [
          ...(config.action
            ? [button(config.actionLabel, config.action, 'primary')]
            : []),
          ...(config.additionalActions || []),
          button('Refresh', () => navigate(route, query, true)),
        ]),
        filterForm(query, config.filters, navigate, route),
      ],
      table(
        config.headers,
        page.items.map(config.row),
        'No ' + config.title.toLowerCase() + ' yet.',
      ),
      pager(page, query, navigate, route, stack),
      config.title,
    ),
  );
}
export async function runsList(
  container,
  query,
  navigate,
  state,
  experiment = null,
) {
  const parameters = Object.fromEntries(query);
  if (experiment) parameters.experiment_id = experiment.experiment_id;
  const page = await get('/runs', parameters);
  const selected = new Set();
  const compare = button(
    'Compare runs (0)',
    () =>
      navigate(
        'compare',
        new URLSearchParams({ runs: [...selected].join(',') }),
      ),
    'secondary',
    { disabled: true },
  );
  const controls = (run) => {
    const input = el('input', {
      type: 'checkbox',
      'aria-label': 'Compare ' + run.display_name,
    });
    input.addEventListener('change', () => {
      if (input.checked && selected.size === 5) {
        input.checked = false;
        toast('Choose at most five runs.');
        return;
      }
      if (input.checked) selected.add(run.run_id);
      else selected.delete(run.run_id);
      compare.textContent = `Compare runs (${selected.size})`;
      compare.disabled = selected.size < 2;
    });
    return input;
  };
  const route = experiment ? 'experiments/' + experiment.experiment_id : 'runs';
  clear(
    container,
    listScreen(
      [
        experiment
          ? el(
              'div',
              { class: 'breadcrumb' },
              link('Experiments', 'experiments'),
              ' / ',
              experiment.display_name,
            )
          : null,
        pageHeader(
          experiment?.display_name || 'Runs',
          experiment?.description ||
            'Inspect execution status, results and logs.',
          [
            button(
              'Create run',
              () =>
                navigate(
                  'runs/new',
                  new URLSearchParams(
                    experiment ? { experiment: experiment.experiment_id } : {},
                  ),
                ),
              'primary',
            ),
            button('Refresh', () => navigate(route, query, true)),
          ],
        ),
        experiment
          ? el(
              'details',
              {},
              el('summary', {}, 'Experiment details'),
              fields([
                ['ID', referenceLabel('experiments', experiment.experiment_id)],
                ['Created', date(experiment.created_at)],
              ]),
            )
          : null,
        filterForm(
          query,
          [
            ['search', 'Search'],
            ...(!experiment ? [['experiment_id', 'Experiment ID']] : []),
            ['definition_id', 'Pipeline ID'],
            ['state', 'State', RUN_STATES],
          ],
          navigate,
          route,
        ),
        el(
          'div',
          { class: 'toolbar' },
          compare,
          el(
            'span',
            { class: 'subtle' },
            'Select 2–5 runs on this page to compare.',
          ),
        ),
      ],
      table(
        [
          '',
          'Name',
          'Status',
          'Created',
          'Duration',
          'Experiment',
          'Pipeline ID',
        ],
        runRows(page.items, controls),
        'No runs yet.',
      ),
      pager(page, query, navigate, route, pageHistory(state, route, query)),
      'Runs',
    ),
  );
}
export async function pipelineDetail(
  container,
  id,
  query,
  navigate,
  state,
  isDefinition = false,
) {
  const catalog = isDefinition ? null : await get('/pipelines/' + id);
  let versions = [];
  let versionTruncated = false;
  if (catalog) {
    const result = await collect('/definitions', { pipeline_id: id });
    versions = result.items;
    versionTruncated = result.truncated;
  }
  const versionId = isDefinition
    ? id
    : query.get('version') || catalog.default_version_id;
  const definition = await get('/definitions/' + versionId);
  if (catalog && definition.pipeline_id !== catalog.pipeline_id)
    throw new Error('This version does not belong to the selected pipeline.');
  const tab = query.get('tab') || 'Graph',
    selected = query.get('node');
  const route = (isDefinition ? 'definitions/' : 'pipelines/') + id;
  function setQuery(key, value) {
    const next = new URLSearchParams(query);
    next.set(key, value);
    navigate(route, next);
  }
  const actions = [
    button(
      'Create run',
      () =>
        navigate(
          'runs/new',
          new URLSearchParams({ definition: definition.definition_id }),
        ),
      'primary',
    ),
  ];
  if (catalog?.registration_origin === 'api')
    actions.push(
      button('Upload version', () =>
        uploadPipeline(catalog, (v) => {
          const next = new URLSearchParams({ version: v.pipeline_version_id });
          navigate(route, next);
        }),
      ),
    );
  const selector = el(
    'select',
    {
      'aria-label': 'Pipeline version',
      onChange: (event) => setQuery('version', event.target.value),
    },
    versions.map((v) =>
      el(
        'option',
        { value: v.definition_id, selected: v.definition_id === versionId },
        `${v.version_name || short(v.definition_id)}${v.definition_id === catalog?.default_version_id ? ' · current default' : ''}`,
      ),
    ),
  );
  const body = el('div');
  let selectionView;
  clear(
    container,
    resourceHeading(
      'Pipelines',
      'pipelines',
      catalog?.name || definition.name || 'Pipeline definition',
      actions,
      null,
      catalog?.description ||
        definition.description ||
        'Immutable compiled definition',
    ),
    catalog
      ? el(
          'div',
          { class: 'detail-meta' },
          referenceLabel('pipelines', catalog.pipeline_id, true),
          labeled('Version', selector),
          referenceLabel('definitions', versionId, true),
        )
      : referenceLabel('definitions', definition.definition_id),
    versionTruncated
      ? notice(
          'Version selector contains the first 2,000 versions. Open a Pipeline ID directly for older history.',
        )
      : null,
    catalog?.registration_origin === 'configuration'
      ? notice(
          'This catalog is configured from a server-side file. Use definitions refresh after changing that file.',
        )
      : null,
    tabs(['Graph', 'Summary', 'Source'], tab, (name) => setQuery('tab', name)),
    body,
  );
  if (tab === 'Graph') {
    const model = graphModel(definition.pipeline_spec),
      byName = new Map(model.nodes.map((n) => [n.name, n]));
    const graphNode = graph(
      definition.pipeline_spec,
      [],
      selected,
      (name) => setQuery('node', name),
      {
        ...graphSettings(query, route, navigate, () => query),
        identity: definition.definition_id,
      },
    );
    selectionView = graphWorkspace(
      body,
      route,
      query,
      navigate,
      graphNode,
      (name) => {
        const node = byName.get(name);
        return node
          ? section(
              node.name,
              fields([
                [
                  'Component',
                  definition.component_ids?.[node.componentKey]
                    ? link(
                        node.componentKey,
                        'components/' +
                          definition.component_ids[node.componentKey],
                      )
                    : node.componentKey,
                ],
                [
                  'Conditional',
                  node.task.triggerPolicy?.condition || 'No condition',
                ],
                ['Kind', node.group ? 'Nested graph' : 'Component'],
              ]),
              el('h3', {}, 'Inputs and outputs'),
              json({
                inputs: node.component.inputDefinitions || {},
                outputs: node.component.outputDefinitions || {},
              }),
              el('h3', {}, 'Task configuration'),
              json(node.task),
            )
          : null;
      },
      (next) => {
        query = next;
      },
    );
  } else if (tab === 'Source') {
    clear(
      body,
      section(
        'Compiled source',
        el(
          'div',
          { class: 'actions source-actions' },
          button('Download source', () =>
            download(
              'pipeline.' +
                (definition.source_text?.trim().startsWith('{')
                  ? 'json'
                  : 'yaml'),
              definition.source_text ||
                JSON.stringify(definition.pipeline_spec, null, 2),
              'text/plain',
            ),
          ),
          button('Copy source', async () => {
            try {
              await navigator.clipboard.writeText(
                definition.source_text ||
                  JSON.stringify(definition.pipeline_spec, null, 2),
              );
              toast('Source copied');
            } catch {
              toast('Clipboard unavailable. Use Download source.');
            }
          }),
        ),
        el(
          'pre',
          { class: 'code' },
          definition.source_text ||
            JSON.stringify(definition.pipeline_spec, null, 2),
        ),
      ),
    );
  } else
    clear(
      body,
      section(
        'Definition',
        fields([
          [
            'Version ID',
            referenceLabel('definitions', definition.definition_id),
          ],
          [
            'Pipeline ID',
            definition.pipeline_id
              ? link(
                  definition.pipeline_id,
                  'pipelines/' + definition.pipeline_id,
                )
              : 'Unregistered inline definition',
          ],
          ['Version name', definition.version_name || '—'],
          ['Created', date(definition.created_at)],
          ['SHA-256', definition.sha256],
          ['Profile', definition.profile],
          ['Available', String(definition.available)],
          [
            'Current default',
            String(definition.default_version_id === definition.definition_id),
          ],
        ]),
      ),
      section(
        'Root interface',
        json({
          inputs: definition.pipeline_spec.root?.inputDefinitions || {},
          outputs: definition.pipeline_spec.root?.outputDefinitions || {},
        }),
      ),
    );
  const screen = detailLayout(container, body, tab);
  screen.detailView = selectionView || { path: route, accepts: () => false };
}
export async function componentDetail(container, id, query, navigate) {
  const component = await get('/components/' + id);
  const tab = query.get('tab') || 'Overview',
    route = 'components/' + id;
  const body = el('div');
  clear(
    container,
    resourceHeading('Components', 'components', component.name || 'Component', [
      button('Refresh', () => navigate(route, query, true)),
    ]),
    el(
      'div',
      { class: 'detail-meta' },
      el('span', { class: 'id' }, component.component_id),
      link(
        'Pipeline ID ' + short(component.definition_id),
        'definitions/' + component.definition_id,
      ),
      el(
        'span',
        {},
        component.executor?.container?.image || 'Graph / importer',
      ),
    ),
    tabs(['Overview', 'Interface', 'Executor', 'Source'], tab, (name) =>
      navigate(route, new URLSearchParams({ tab: name })),
    ),
    body,
  );
  if (tab === 'Interface')
    clear(
      body,
      section(
        'Interface',
        json({
          inputs: component.compiled?.inputDefinitions || {},
          outputs: component.compiled?.outputDefinitions || {},
        }),
      ),
    );
  else if (tab === 'Executor')
    clear(body, section('Executor', json(component.executor)));
  else if (tab === 'Source')
    clear(body, section('Compiled contract', json(component.compiled)));
  else
    clear(
      body,
      section(
        'Component',
        fields([
          ['Name', component.name],
          [
            'Component ID',
            referenceLabel('components', component.component_id),
          ],
          [
            'Pipeline ID',
            link(
              component.definition_id,
              'definitions/' + component.definition_id,
            ),
          ],
          ['Created', date(component.created_at)],
          ['Image', component.executor?.container?.image || 'Graph / importer'],
        ]),
      ),
    );
  const screen = detailLayout(container, body, tab);
  screen.detailView = { path: route, accepts: () => false };
}
export async function artifactDetail(container, id, query, navigate, state) {
  const artifact = await get('/artifacts/' + id);
  const tab = query.get('tab') || 'Contents',
    route = 'artifacts/' + id;
  const pin = button(artifact.pinned ? 'Unpin' : 'Pin', () =>
    confirmAction(
      artifact.pinned ? 'Unpin artifact' : 'Pin artifact',
      artifact.pinned
        ? 'Remove the explicit retention pin? Other history protections remain.'
        : 'Protect this artifact with an explicit retention pin?',
      () =>
        post('/artifacts/' + id + (artifact.pinned ? '/unpin' : '/pin'), {}),
      () => navigate(route, query, true),
    ),
  );
  const body = el('div');
  clear(
    container,
    resourceHeading(
      'Artifacts',
      'artifacts',
      artifact.version || artifact.upload?.filename || short(id),
      [
        pin,
        button(
          'Delete artifact',
          () => deleteResource('artifacts', id, () => navigate('artifacts')),
          'danger',
        ),
        link('Storage cleanup', 'storage'),
        button('Refresh', () => navigate(route, query, true)),
      ],
      badge(artifact.availability),
    ),
    el(
      'div',
      { class: 'detail-meta' },
      el('span', { class: 'id' }, id),
      el('span', {}, artifact.type.schema_title),
      badge(artifact.publication_state),
      el('span', {}, artifact.pinned ? 'Pinned' : 'Not explicitly pinned'),
      !artifact.producer ||
        artifact.creation_origin === 'manual' ||
        artifact.origin === 'external'
        ? el('span', {}, 'Manually added · explicit deletion only')
        : null,
    ),
    tabs(['Contents', 'Overview', 'Lineage'], tab, (name) =>
      navigate(route, new URLSearchParams({ tab: name })),
    ),
    body,
  );
  if (tab === 'Contents') {
    body.classList.add('list-body');
    clear(body, await artifactContents(artifact, query, navigate, state));
  } else if (tab === 'Lineage') {
    body.classList.add('list-body');
    const lineage = await get('/artifacts/' + id + '/lineage', {
      page_token: query.get('page_token'),
    });
    const producer = lineage.producer;
    clear(
      body,
      listScreen(
        [
          el('h2', {}, 'Original producer'),
          producer
            ? el(
                'details',
                {},
                el('summary', {}, 'Producer details'),
                fields(
                  Object.entries(producer).map(([key, value]) => [
                    key,
                    lineage.deleted_producer_ids?.includes(value)
                      ? value + ' (deleted)'
                      : key === 'run_id'
                        ? link(value, 'runs/' + value)
                        : key === 'task_id'
                          ? link(value, 'tasks/' + value)
                          : key === 'attempt_id'
                            ? link(value, 'attempts/' + value)
                            : String(value),
                  ]),
                ),
              )
            : notice('External artifact: no Dockflow producer.'),
          el('h2', {}, 'Consumer tasks'),
          el(
            'p',
            { class: 'subtle' },
            'Tasks that recorded this artifact as an input. Reuse keeps the original producer identity.',
          ),
        ],
        table(
          ['Task', 'Run', 'State'],
          lineage.items.map((t) => [
            link(t.name, 'tasks/' + t.task_id),
            link(short(t.run_id), 'runs/' + t.run_id),
            badge(t.state),
          ]),
          'No consumer tasks.',
        ),
        pager(
          lineage,
          query,
          navigate,
          route,
          pageHistory(state, route, query),
        ),
        'Artifact consumers',
      ),
    );
  } else {
    const metrics = Object.entries(artifact.metadata || {}).filter(
      ([, v]) => typeof v === 'number' && Number.isFinite(v),
    );
    clear(
      body,
      metrics.length
        ? el(
            'div',
            { class: 'metric-grid' },
            metrics.map(([name, value]) =>
              el(
                'div',
                { class: 'metric' },
                el('small', {}, name),
                el('strong', {}, String(value)),
              ),
            ),
          )
        : null,
      section(
        'Artifact',
        fields([
          ['Artifact ID', id],
          [
            'Type',
            artifact.type.schema_title + ' @ ' + artifact.type.schema_version,
          ],
          ['Origin', artifact.origin],
          ['Ownership', artifact.ownership],
          ['Created', date(artifact.created_at)],
          ['Content URI', artifact.content_uri],
          ['Source URI', artifact.source_uri],
          ...(artifact.upload
            ? [
                ['Uploaded file', artifact.upload.filename],
                [
                  'ZIP handling',
                  artifact.upload.archive_mode === 'extract'
                    ? 'Extracted directory'
                    : 'Kept as a file',
                ],
              ]
            : []),
          ['Descriptor URI', artifact.uri],
          ['Data revision', artifact.version],
          [
            'Producer',
            artifact.producer
              ? fields(
                  Object.entries(artifact.producer).map(([key, value]) => {
                    const collection = {
                      run_id: 'runs',
                      task_id: 'tasks',
                      attempt_id: 'attempts',
                      definition_id: 'definitions',
                      component_id: 'components',
                    }[key];
                    return [
                      key,
                      collection
                        ? link(String(value), collection + '/' + value)
                        : String(value),
                    ];
                  }),
                )
              : 'External',
          ],
        ]),
      ),
      section('Metadata', json(artifact.metadata)),
      section(
        'Fingerprint and inventory',
        json({
          fingerprint: artifact.fingerprint,
          inventory: artifact.inventory,
          size_bytes: artifact.size_bytes,
          payload_kind: artifact.payload_kind,
        }),
      ),
      el(
        'details',
        {},
        el('summary', {}, 'Complete artifact descriptor'),
        json(artifact),
      ),
      notice(
        'Contents provides bounded previews of registered files. Payload URIs remain text; HTML and scripts are never rendered.',
      ),
    );
  }
  const screen = detailLayout(container, body, tab);
  screen.detailView = { path: route, accepts: () => false };
}
export function logsView(runId, query = {}) {
  let cursor,
    buffer = [],
    bytes = 0,
    dropped = false;
  const output = el(
    'div',
    { class: 'logs', tabindex: '0', 'aria-label': 'Execution logs' },
    'No log entries loaded.',
  );
  const status = el('span', { class: 'subtle' }),
    errors = el('div');
  const stream = el(
    'select',
    { 'aria-label': 'Log stream' },
    ...['all', 'stdout', 'stderr', 'system'].map((s) =>
      el('option', { value: s }, s === 'all' ? 'All streams' : s),
    ),
  );
  function render() {
    clear(
      output,
      ...plainLogEntries(buffer)
        .filter((e) => stream.value === 'all' || e.stream === stream.value)
        .map((e) =>
          el(
            'span',
            { class: 'log-entry ' + e.stream },
            `[${e.timestamp}] [${e.stream}] ${e.text}`,
          ),
        ),
    );
    if (!output.childNodes.length)
      output.textContent = 'No output for this selection yet.';
  }
  stream.addEventListener('change', render);
  const restart = button('Start from beginning', () => {
    cursor = undefined;
    buffer = [];
    bytes = 0;
    dropped = false;
    more.click();
  });
  const more = button('Load logs', async () => {
    more.disabled = true;
    restart.disabled = true;
    clear(errors);
    try {
      const page = await get('/runs/' + runId + '/logs', {
        ...query,
        cursor,
        limit_bytes: 65536,
      });
      cursor = page.next_cursor;
      for (const entry of page.entries) {
        buffer.push(entry);
        bytes += new TextEncoder().encode(entry.text).byteLength;
      }
      while (bytes > 1024 * 1024 && buffer.length > 1) {
        bytes -= new TextEncoder().encode(buffer.shift().text).byteLength;
        dropped = true;
      }
      render();
      status.textContent =
        (page.terminal
          ? 'All retained logs loaded.'
          : 'Refresh to load more output.') +
        (dropped
          ? ' Earlier display entries were dropped from the 1 MiB browser buffer.'
          : '');
      more.textContent = page.terminal ? 'Refresh logs' : 'Load more / refresh';
    } catch (error) {
      if (error.name !== 'AbortError') clear(errors, errorBox(error));
    } finally {
      more.disabled = false;
      restart.disabled = false;
    }
  });
  const node = el(
    'div',
    {},
    el('div', { class: 'toolbar' }, stream, more, restart),
    errors,
    output,
    status,
  );
  queueMicrotask(() => more.click());
  return node;
}
function taskPanel(task, spec, definition, query, navigate, route) {
  const tab = query.get('stepTab') || 'Overview';
  const body = el('div');
  const panel = el(
    'section',
    { class: 'panel step-panel' },
    el('h2', {}, task?.name || spec?.name || 'Step'),
    task ? badge(task.state) : notice('This step has no execution record yet.'),
    tabs(['Overview', 'Inputs / outputs', 'Attempts', 'Logs'], tab, (name) => {
      const next = new URLSearchParams(query);
      next.set('stepTab', name);
      navigate(route, next);
    }),
    body,
  );
  if (!task) {
    clear(body, json(spec?.task || {}));
    return panel;
  }
  if (tab === 'Inputs / outputs')
    clear(
      body,
      el('h3', {}, 'Input parameters'),
      json(task.parameters || {}),
      el('h3', {}, 'Input artifacts'),
      artifactLinks(task.inputs),
      el('h3', {}, 'Output parameters'),
      json(task.output_parameters || {}),
      el('h3', {}, 'Output artifacts'),
      artifactLinks(task.outputs),
    );
  else if (tab === 'Attempts')
    clear(
      body,
      task.state === 'reused'
        ? notice(
            'This task reused committed outputs. No new attempt was executed.',
          )
        : null,
      task.reuse?.producer_attempt_id
        ? link(
            'Original producer attempt',
            'attempts/' + task.reuse.producer_attempt_id,
          )
        : null,
      task.attempt_ids?.length
        ? el(
            'ol',
            {},
            task.attempt_ids.map((id, index) =>
              el(
                'li',
                {},
                link(
                  'Attempt ' + (index + 1) + ' · ' + short(id),
                  'attempts/' + id,
                ),
              ),
            ),
          )
        : el('p', { class: 'subtle' }, 'No attempts.'),
    );
  else if (tab === 'Logs')
    clear(body, logsView(task.run_id, { task_id: task.task_id }));
  else
    clear(
      body,
      fields([
        ['Task ID', link(task.task_id, 'tasks/' + task.task_id)],
        [
          'Component',
          task.component_id
            ? link(short(task.component_id), 'components/' + task.component_id)
            : '—',
        ],
        ['Disposition', task.disposition || '—'],
        ['Created', date(task.created_at)],
        ['Attempts', String(task.attempt_ids?.length || 0)],
        [
          'Image',
          definition.pipeline_spec.deploymentSpec?.executors?.[
            spec?.component?.executorLabel
          ]?.container?.image || 'Graph / importer',
        ],
      ]),
      task.reuse
        ? section(
            'Reuse',
            task.reuse.producer_attempt_id
              ? link(
                  'Original producer',
                  'attempts/' + task.reuse.producer_attempt_id,
                )
              : null,
            json(task.reuse),
          )
        : null,
      task.error
        ? errorBox({
            message:
              typeof task.error === 'string'
                ? task.error
                : JSON.stringify(task.error),
          })
        : null,
      el('details', {}, el('summary', {}, 'Complete task record'), json(task)),
    );
  return panel;
}
export async function runDetail(container, id, query, navigate, state) {
  const run = await get('/runs/' + id);
  const [definition, result] = await Promise.all([
    get('/definitions/' + run.definition_id),
    collect('/tasks', { run_id: id }),
  ]);
  const tasks = result.items;
  const tab = query.get('tab') || 'Graph',
    selected = query.get('node'),
    route = 'runs/' + id;
  state.currentRun = run;
  const actions = [
    ...(terminal.has(run.state)
      ? [
          button(
            'Delete run',
            () => deleteResource('runs', id, () => navigate('runs')),
            'danger',
          ),
        ]
      : []),
    button('Clone run', () =>
      navigate('runs/new', new URLSearchParams({ clone: id })),
    ),
  ];
  if (!terminal.has(run.state))
    actions.push(
      button(
        'Cancel run',
        () =>
          confirmAction(
            'Cancel run',
            'Cancel this run? Completed results remain recorded; active work will stop under the service cancellation policy.',
            () => post('/runs/' + id + '/cancel', {}),
            () => navigate(route, query, true),
          ),
        'danger',
      ),
    );
  actions.push(button('Refresh', () => navigate(route, query, true)));
  const auto = el('input', { type: 'checkbox', checked: state.autoRefresh });
  auto.addEventListener('change', () => {
    state.autoRefresh = auto.checked;
    state.schedule?.();
  });
  const body = el('div');
  let selectionView;
  clear(
    container,
    resourceHeading(
      'Runs',
      'runs',
      run.display_name,
      actions,
      badge(run.state),
    ),
    el(
      'div',
      { class: 'detail-meta' },
      referenceLabel('runs', id, true),
      el('span', {}, 'Created ' + date(run.created_at)),
      el('span', {}, 'Duration ' + duration(run)),
      link(
        'Experiment ' + short(run.experiment_id),
        'experiments/' + run.experiment_id,
      ),
      link(
        'Version ' + short(run.definition_id),
        'definitions/' + run.definition_id,
      ),
      !terminal.has(run.state)
        ? el('label', { class: 'inline-check' }, auto, 'Live updates every 3s')
        : null,
    ),
    run.error
      ? errorBox({
          message:
            typeof run.error === 'string'
              ? run.error
              : JSON.stringify(run.error),
        })
      : null,
    run.reconciliation_required
      ? notice(
          'Execution recovery is required. The service must confirm prior work has stopped before replacement execution.',
          'error',
        )
      : null,
    tabs(['Graph', 'Details', 'Artifacts', 'Logs'], tab, (name) => {
      const next = new URLSearchParams(query);
      next.set('tab', name);
      navigate(route, next);
    }),
    body,
  );
  if (tab === 'Graph') {
    const model = graphModel(definition.pipeline_spec),
      byName = new Map(model.nodes.map((n) => [n.name, n]));
    clear(
      body,
      result.truncated
        ? notice(
            'Showing the first 2,000 task records; inspect an individual task ID for additional history.',
          )
        : null,
    );
    const graphNode = graph(
      definition.pipeline_spec,
      tasks,
      selected,
      (name) => {
        const next = new URLSearchParams(query);
        next.set('node', name);
        navigate(route, next);
      },
      {
        ...graphSettings(query, route, navigate, () => query),
        identity: definition.definition_id,
      },
    );
    selectionView = graphWorkspace(
      body,
      route,
      query,
      navigate,
      graphNode,
      (name, next) =>
        taskPanel(
          tasks.find((task) => task.name === name),
          byName.get(name),
          definition,
          next,
          navigate,
          route,
        ),
      (next) => {
        query = next;
      },
    );
  } else if (tab === 'Details')
    clear(
      body,
      section(
        'Invocation',
        fields([
          ['Run ID', referenceLabel('runs', id)],
          [
            'Pipeline ID',
            link(run.definition_id, 'definitions/' + run.definition_id),
          ],
          [
            'Experiment',
            link(run.experiment_id, 'experiments/' + run.experiment_id),
          ],
          ['Description', run.description],
          ['Created', date(run.created_at)],
          ['Started', date(run.started_at)],
          ['Finished', date(run.finished_at)],
          ['Reuse', JSON.stringify(run.reuse)],
        ]),
      ),
      section('Parameters', json(run.parameters)),
      section(
        'Selection and historical bindings',
        json({
          selection: run.selection,
          bindings: run.bindings,
          use_executions: run.use_executions,
          resolved_plan: run.resolved_plan,
        }),
      ),
      el(
        'details',
        {},
        el('summary', {}, 'Complete accepted run record'),
        json(run),
      ),
    );
  else if (tab === 'Artifacts') {
    body.classList.add('list-body');
    clear(
      body,
      localList(
        ['Step', 'Status', 'Artifacts', 'Output parameters'],
        tasks.map((t) => [
          link(t.name, 'tasks/' + t.task_id),
          badge(t.state),
          artifactLinks(t.outputs),
          json(t.output_parameters || {}),
        ]),
        {
          title: 'Task results',
          limited: result.truncated,
          header: el(
            'div',
            {},
            el('h2', {}, 'Task results'),
            el(
              'details',
              {},
              el('summary', {}, 'Pipeline inputs and outputs'),
              section('Pipeline inputs', artifactLinks(run.inputs)),
              section('Pipeline outputs', artifactLinks(run.outputs)),
            ),
          ),
        },
      ),
    );
  } else clear(body, section('Run logs', logsView(id)));
  const screen = detailLayout(container, body, tab);
  screen.detailView = selectionView || { path: route, accepts: () => false };
  return run;
}
export async function executionDetail(container, kind, id, query, navigate) {
  const record = await get('/' + kind + '/' + id);
  const task =
    kind === 'tasks' ? record : await get('/tasks/' + record.task_id);
  const tab = query.get('tab') || 'Overview',
    route = kind + '/' + id;
  const body = el('div');
  clear(
    container,
    resourceHeading(
      'Executions',
      'executions',
      kind === 'tasks' ? task.name : 'Attempt ' + short(id),
      [
        ...(kind === 'attempts' && terminal.has(record.state)
          ? [
              button(
                'Delete execution',
                () =>
                  deleteResource('attempts', id, () => navigate('executions')),
                'danger',
              ),
            ]
          : []),
        button('Open in graph', () =>
          navigate(
            'runs/' + record.run_id,
            new URLSearchParams({ node: task.name }),
          ),
        ),
        button('Refresh', () => navigate(route, query, true)),
      ],
      badge(record.state),
    ),
    el(
      'div',
      { class: 'detail-meta' },
      referenceLabel(kind, id, true),
      link('Run ' + short(record.run_id), 'runs/' + record.run_id),
      link(task.name, 'tasks/' + task.task_id),
      kind === 'attempts'
        ? el('span', {}, 'Duration ' + duration(record))
        : null,
    ),
    tabs(['Overview', 'Inputs / outputs', 'Logs', 'Record'], tab, (name) =>
      navigate(route, new URLSearchParams({ tab: name })),
    ),
    body,
  );
  if (tab === 'Inputs / outputs')
    clear(
      body,
      section('Parameters', json(record.parameters)),
      section('Inputs', artifactLinks(record.inputs)),
      section(
        'Outputs',
        artifactLinks(record.outputs),
        json(record.output_parameters || {}),
      ),
    );
  else if (tab === 'Logs')
    clear(
      body,
      section(
        'Logs',
        logsView(
          record.run_id,
          kind === 'tasks' ? { task_id: id } : { attempt_id: id },
        ),
      ),
    );
  else if (tab === 'Record')
    clear(body, section('Complete record', json(record)));
  else
    clear(
      body,
      section(
        'Execution',
        fields([
          ['Run', link(record.run_id, 'runs/' + record.run_id)],
          ['Task', link(task.name, 'tasks/' + task.task_id)],
          ['Exit status', record.exit_status ?? '—'],
          ['Publication', record.publication_state ?? '—'],
          ['Image', record.image ? json(record.image) : '—'],
        ]),
      ),
      record.error ? section('Error', json(record.error)) : null,
      task.reuse?.producer_attempt_id
        ? section(
            'Reused producer',
            link(
              task.reuse.producer_attempt_id,
              'attempts/' + task.reuse.producer_attempt_id,
            ),
            json(task.reuse),
          )
        : null,
      kind === 'tasks'
        ? section(
            'Attempts',
            task.attempt_ids?.length
              ? el(
                  'ol',
                  {},
                  task.attempt_ids.map((aid, i) =>
                    el(
                      'li',
                      {},
                      link(
                        'Attempt ' + (i + 1) + ' · ' + short(aid),
                        'attempts/' + aid,
                      ),
                    ),
                  ),
                )
              : el(
                  'p',
                  { class: 'subtle' },
                  'No actual attempts for this task.',
                ),
          )
        : null,
    );
  if (kind === 'attempts') {
    const heading = container.querySelector('h1');
    heading.dataset.referenceCollection = 'attempts';
    heading.dataset.referenceId = id;
  }
  const screen = detailLayout(container, body, tab);
  screen.detailView = { path: route, accepts: () => false };
}
export async function compareRuns(container, query) {
  const ids = [
    ...new Set((query.get('runs') || '').split(',').filter(Boolean)),
  ];
  if (ids.length < 2 || ids.length > 5)
    throw new Error('Choose two to five run IDs to compare.');
  const records = await Promise.all(
    ids.map(async (id) => {
      const run = await get('/runs/' + id),
        tasks = await collect('/tasks', { run_id: id });
      const values = new Map(
        Object.entries(run.parameters || {}).map(([name, value]) => [
          'Parameter · ' + name,
          { value },
        ]),
      );
      const artifactIds = new Map();
      for (const task of tasks.items) {
        for (const [name, value] of Object.entries(
          task.output_parameters || {},
        ))
          values.set(`Output · ${task.name}.${name}`, { value });
        for (const [name, aid] of Object.entries(task.outputs || {}))
          artifactIds.set(`${task.name}.${name}`, aid);
      }
      let limited = tasks.truncated;
      const entries = [...artifactIds];
      if (entries.length > 200) limited = true;
      // Limit concurrent requests to avoid overwhelming the single-project owner.
      for (let offset = 0; offset < Math.min(entries.length, 200); offset += 8)
        await Promise.all(
          entries
            .slice(offset, Math.min(offset + 8, 200))
            .map(async ([name, aid]) => {
              try {
                const artifact = await get('/artifacts/' + aid);
                for (const [metric, value] of Object.entries(
                  artifact.metadata || {},
                ))
                  if (typeof value === 'number' && Number.isFinite(value))
                    values.set(`Metric · ${name}.${metric}`, {
                      value,
                      artifact: aid,
                    });
              } catch (error) {
                if (error.name === 'AbortError') throw error;
                values.set(`Artifact · ${name}`, {
                  value: 'Unavailable: ' + error.message,
                  artifact: aid,
                });
              }
            }),
        );
      return { run, values, limited };
    }),
  );
  const keys = [
    ...new Set(records.flatMap((r) => [...r.values.keys()])),
  ].sort();
  const rows = [
    ['Status', ...records.map((r) => badge(r.run.state))],
    [
      'Pipeline ID',
      ...records.map((r) =>
        link(short(r.run.definition_id), 'definitions/' + r.run.definition_id),
      ),
    ],
    ['Duration', ...records.map((r) => duration(r.run))],
    ...keys.map((key) => [
      key,
      ...records.map((r) => {
        const entry = r.values.get(key);
        if (!entry) return el('span', { class: 'muted-value' }, 'Absent');
        return el(
          'div',
          {},
          typeof entry.value === 'object'
            ? json(entry.value)
            : String(entry.value),
          entry.artifact
            ? el(
                'div',
                {},
                link('Source artifact', 'artifacts/' + entry.artifact),
              )
            : null,
        );
      }),
    ]),
  ];
  clear(
    container,
    localList(
      [
        'Field',
        ...records.map((r) => link(r.run.display_name, 'runs/' + r.run.run_id)),
      ],
      rows,
      {
        title: 'Comparison fields',
        limited: records.some((r) => r.limited),
        header: [
          el(
            'div',
            { class: 'breadcrumb' },
            link('Runs', 'runs'),
            ' / Compare',
          ),
          pageHeader(
            'Compare runs',
            `${records.length} runs · recorded parameters and scalar results`,
          ),
          records.some((r) => r.limited)
            ? notice(
                'Comparison is limited to 2,000 tasks and 200 output artifacts per run. Open individual runs for complete history.',
              )
            : null,
        ],
      },
    ),
  );
  container.firstElementChild.classList.add('comparison');
}
export async function serviceInfo(container, navigate) {
  const capabilities = await get('/capabilities');
  let health;
  try {
    health = await request('/health/ready');
  } catch (error) {
    if (error.status !== 503) throw error;
    health = error.data || { status: 'unavailable' };
  }
  const body = el('div');
  clear(
    container,
    resourceHeading(
      'Service',
      'service',
      'Service information',
      [
        button('Refresh', () =>
          navigate('service', new URLSearchParams(), true),
        ),
      ],
      badge(health.status),
    ),
    el(
      'div',
      { class: 'detail-meta' },
      el('span', {}, capabilities.project_id),
      el('span', {}, capabilities.profile),
    ),
    body,
  );
  clear(
    body,
    section(
      'Runtime',
      fields([
        ['Project', capabilities.project_id],
        ['Profile', capabilities.profile],
        ['Qualification', capabilities.qualification],
        ['Execution', capabilities.backends.execution],
        ['Metadata', capabilities.backends.metadata],
        ['Active runs', String(capabilities.limits.active_runs)],
        ['Task parallelism', String(capabilities.limits.task_parallelism)],
        ['Queue capacity', String(capabilities.limits.queue_capacity)],
      ]),
    ),
    section('Readiness', badge(health.status), json(health.checks || {})),
    section('Versions', fields(Object.entries(capabilities.versions))),
    section(
      'Features',
      el(
        'div',
        { class: 'actions' },
        capabilities.features.map((f) => badge(f)),
      ),
    ),
    section(
      'Limits',
      el(
        'ul',
        {},
        capabilities.limitations.map((text) => el('li', {}, text)),
      ),
    ),
    section('Complete capabilities', json(capabilities)),
  );
  const screen = detailLayout(container, body);
  screen.detailView = { path: 'service', accepts: () => false };
}
