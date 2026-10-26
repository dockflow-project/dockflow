import { el, clear, button, link, errorBox, notice, empty } from './dom.js';
import {
  get,
  request,
  newPage,
  hasToken,
  forgetToken,
  authenticate,
} from './api.js';
import { runForm } from './forms.js';
import { storageCleanup } from './cleanup.js';
import { watchReferences } from './references.js';
import {
  collection,
  pipelineDetail,
  runsList,
  componentDetail,
  artifactDetail,
  runDetail,
  executionDetail,
  compareRuns,
  serviceInfo,
  terminal,
} from './views.js';

const content = document.getElementById('content');
const references = watchReferences(content, document.getElementById('modal'));
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  content.focus();
});
const state = {
  pages: {},
  autoRefresh: true,
  currentRun: null,
  schedule: null,
};
let generation = 0,
  timer,
  connected = false;
const groups = [
  [
    'Definitions',
    [
      ['pipelines', '◇', 'Pipelines'],
      ['components', '▦', 'Components'],
    ],
  ],
  [
    'Workloads',
    [
      ['experiments', '◫', 'Experiments'],
      ['runs', '▷', 'Runs'],
      ['executions', '≋', 'Executions'],
    ],
  ],
  [
    'Storage',
    [
      ['artifacts', '⬡', 'Artifacts'],
      ['storage', '▤', 'Cleanup'],
    ],
  ],
];
const items = groups.flatMap(([, entries]) => entries);
const navigation = document.getElementById('navigation');
for (const [name, entries] of groups) {
  const heading = 'navigation-' + name.toLowerCase();
  navigation.append(
    el(
      'div',
      { class: 'nav-section', role: 'group', 'aria-labelledby': heading },
      el('h2', { id: heading, class: 'nav-section-title' }, name),
      entries.map(([path, icon, label]) =>
        link(
          [
            el('span', { class: 'nav-icon', 'aria-hidden': 'true' }, icon),
            el('span', { class: 'nav-text' }, label),
          ],
          path,
          { 'aria-label': label, title: label, dataset: { route: path } },
        ),
      ),
    ),
  );
}
function current() {
  const [path, qs] = (location.hash.slice(2) || 'pipelines').split('?');
  return { path, query: new URLSearchParams(qs) };
}
function navigate(path, query = new URLSearchParams(), refresh = false) {
  const next = '#/' + path + (query.size ? '?' + query : '');
  if (location.hash === next || refresh) {
    if (location.hash !== next) history.replaceState(null, '', next);
    render(false, refresh);
  } else location.hash = next;
}
function connection(label, ok = true) {
  const node = document.getElementById('connection');
  node.textContent = label;
  node.style.color = ok ? '#287952' : '#ad4c42';
}
function connectButton() {
  document.getElementById('connect').textContent = hasToken()
    ? 'Sign out'
    : 'Connect';
}
function signedOut(message = 'Connect to view this project.') {
  generation++;
  clearTimeout(timer);
  forgetToken();
  references.reset(true);
  const dialog = document.getElementById('modal');
  if (dialog.dataset.kind !== 'authentication') {
    if (dialog.open) dialog.close();
    clear(dialog);
  }
  connected = false;
  state.currentRun = null;
  state.pages = {};
  state.cleanup = null;
  state.contentsTrees = null;
  content.classList.remove('detail-mode', 'list-mode');
  document.getElementById('project-name').textContent = 'Not connected';
  document.getElementById('project-name').removeAttribute('title');
  connection('Not connected', false);
  connectButton();
  clear(
    content,
    empty('Connect to Dockflow', message),
    button('Connect', () => authenticate(() => render()), 'primary'),
  );
}
document.getElementById('connect').addEventListener('click', () => {
  if (hasToken())
    signedOut('Token cleared. Reloading also clears the in-memory token.');
  else authenticate(() => render());
});
window.addEventListener('dockflow:unauthorized', () => {
  signedOut('This service requires a valid bearer token.');
  if (
    !document.getElementById('modal').open ||
    document.getElementById('modal').dataset.kind !== 'authentication'
  )
    authenticate(() => render());
});
async function identify() {
  const result = await get('/capabilities');
  document.getElementById('project-name').textContent =
    result.project_id || 'Current project';
  document.getElementById('project-name').title =
    result.project_id || 'Current project';
  connected = true;
  connectButton();
  try {
    const ready = await request('/health/ready');
    connection(
      ready.status === 'ready' ? 'Service ready' : 'Service unavailable',
      ready.status === 'ready',
    );
  } catch (error) {
    if (error.status === 503) connection('Recovery / unavailable', false);
    else if (error.name !== 'AbortError') connection('Connection lost', false);
  }
}
function schedule() {
  clearTimeout(timer);
  const { path, query } = current();
  if (
    !state.autoRefresh ||
    document.hidden ||
    !state.currentRun ||
    terminal.has(state.currentRun.state) ||
    !path.startsWith('runs/') ||
    path === 'runs/new' ||
    query.get('tab') === 'Logs' ||
    query.get('stepTab') === 'Logs'
  )
    return;
  timer = setTimeout(() => {
    if (
      document.getElementById('modal').open ||
      document.querySelector('.graph-viewport.is-panning') ||
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)
    ) {
      schedule();
      return;
    }
    render(true);
  }, 3000);
}
state.schedule = schedule;
async function render(silent = false, force = false) {
  clearTimeout(timer);
  const turn = ++generation;
  newPage();
  references.reset();
  const { path, query } = current();
  const [kind, id] = path.split('/');
  const mounted = content.querySelector('.detail-screen')?.detailView;
  if (!silent && !force && mounted?.accepts(path, query)) {
    mounted.updateQuery(query);
    references.scan();
    schedule();
    return;
  }
  const staged = el('div');
  const sameDetail = mounted?.path === path;
  const sameList =
    content.classList.contains('list-mode') && content.dataset.route === path;
  const sameQuery = content.dataset.query === query.toString();
  if (!silent && !sameDetail && !sameList) {
    content.classList.remove('detail-mode', 'list-mode');
    clear(content, el('div', { class: 'loading', role: 'status' }, 'Loading…'));
  }
  state.currentRun = null;
  const section =
    kind === 'tasks' || kind === 'attempts'
      ? 'executions'
      : kind === 'definitions'
        ? 'pipelines'
        : kind === 'compare'
          ? 'runs'
          : kind;
  navigation.querySelectorAll('a').forEach((node) => {
    const active = node.dataset.route === section;
    node.classList.toggle('active', active);
    if (active) node.setAttribute('aria-current', 'page');
    else node.removeAttribute('aria-current');
  });
  try {
    if (!connected || silent || kind === 'service') await identify();
    if (kind === 'storage' && !id) await storageCleanup(staged, state);
    else if (kind === 'runs' && id === 'new')
      await runForm(staged, query, navigate);
    else if (kind === 'pipelines' && id)
      await pipelineDetail(staged, id, query, navigate, state);
    else if (kind === 'definitions' && id)
      await pipelineDetail(staged, id, query, navigate, state, true);
    else if (kind === 'experiments' && id)
      await runsList(
        staged,
        query,
        navigate,
        state,
        await get('/experiments/' + id),
      );
    else if (kind === 'runs' && id)
      await runDetail(staged, id, query, navigate, state);
    else if (kind === 'components' && id)
      await componentDetail(staged, id, query, navigate);
    else if (kind === 'artifacts' && id)
      await artifactDetail(staged, id, query, navigate, state);
    else if ((kind === 'tasks' || kind === 'attempts') && id)
      await executionDetail(staged, kind, id, query, navigate);
    else if (kind === 'compare') await compareRuns(staged, query);
    else if (kind === 'service') await serviceInfo(staged, navigate);
    else if (items.some((item) => item[0] === kind) && !id)
      await collection(
        staged,
        kind === 'executions' ? 'attempts' : kind,
        query,
        navigate,
        state,
      );
    else
      clear(
        staged,
        empty('Page not found'),
        link('Go to pipelines', 'pipelines'),
      );
    if (turn !== generation) return;
    // Capture at commit time so panning/zooming during a request is retained.
    const graphViewport = sameDetail
      ? content.querySelector('.graph')?.captureViewport?.()
      : null;
    const scrollPositions = [
      ...content.querySelectorAll(
        '.graph-viewport,.step-panel,.list-content,.detail-context,.detail-body:not(.graph-body):not(.list-body)',
      ),
    ].map((node) => ({ left: node.scrollLeft, top: node.scrollTop }));
    const localPage = sameQuery
      ? content.querySelector('.list-screen')?.capturePage?.()
      : null;
    content.classList.toggle(
      'detail-mode',
      Boolean(staged.querySelector('.detail-screen')),
    );
    content.classList.toggle(
      'list-mode',
      Boolean(staged.firstElementChild?.classList.contains('list-screen')),
    );
    clear(content, ...staged.childNodes);
    references.scan();
    content.dataset.route = path;
    content.dataset.query = query.toString();
    content.querySelector('.list-screen')?.restorePage?.(localPage);
    content.querySelector('.graph')?.restoreViewport?.(graphViewport);
    document.title =
      (content.querySelector('h1')?.textContent || 'Workspace') + ' · Dockflow';
    if (silent || ((sameList || sameDetail) && sameQuery))
      [
        ...content.querySelectorAll(
          '.graph-viewport,.step-panel,.list-content,.detail-context,.detail-body:not(.graph-body):not(.list-body)',
        ),
      ].forEach((node, index) => {
        if (scrollPositions[index]) {
          node.scrollLeft = scrollPositions[index].left;
          node.scrollTop = scrollPositions[index].top;
        }
      });
    schedule();
  } catch (error) {
    if (
      turn !== generation ||
      error.name === 'AbortError' ||
      error.status === 401
    )
      return;
    if (silent || sameList || sameDetail) {
      content.querySelector('.refresh-error')?.remove();
      const warning = errorBox(error, () => render(true));
      warning.classList.add('refresh-error');
      (content.querySelector('.detail-header,.list-header') || content).prepend(
        warning,
      );
      connection('Update failed · data may be stale', false);
    } else {
      content.classList.remove('detail-mode', 'list-mode');
      clear(
        content,
        errorBox(error, () => render()),
      );
    }
  }
}
window.addEventListener('hashchange', () => render());
document.addEventListener('visibilitychange', () => {
  if (document.hidden) clearTimeout(timer);
  else schedule();
});
window.addEventListener('pagehide', () => {
  forgetToken();
  clearTimeout(timer);
});
if (!location.hash) history.replaceState(null, '', '#/pipelines');
render();
