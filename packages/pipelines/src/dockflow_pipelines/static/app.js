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
const items = [
  ['pipelines', '◇', 'Pipelines'],
  ['experiments', '◫', 'Experiments'],
  ['runs', '▷', 'Runs'],
  ['artifacts', '⬡', 'Artifacts'],
  ['executions', '≋', 'Executions'],
  ['components', '▦', 'Components'],
];
const navigation = document.getElementById('navigation');
for (const [path, icon, label] of items)
  navigation.append(
    link(el('span', { class: 'nav-icon', 'aria-hidden': 'true' }, icon), path, {
      'aria-label': label,
    }),
  );
[...navigation.children].forEach((node, index) =>
  node.append(el('span', { class: 'nav-text' }, items[index][2])),
);
function current() {
  const [path, qs] = (location.hash.slice(2) || 'pipelines').split('?');
  return { path, query: new URLSearchParams(qs) };
}
function navigate(path, query = new URLSearchParams(), refresh = false) {
  const next = '#/' + path + (query.size ? '?' + query : '');
  if (location.hash === next || refresh) {
    if (location.hash !== next) history.replaceState(null, '', next);
    render();
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
  connected = false;
  state.currentRun = null;
  state.pages = {};
  document.getElementById('project-name').textContent = 'Not connected';
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
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)
    ) {
      schedule();
      return;
    }
    render(true);
  }, 3000);
}
state.schedule = schedule;
async function render(silent = false) {
  clearTimeout(timer);
  const turn = ++generation;
  newPage();
  const { path, query } = current();
  const [kind, id] = path.split('/');
  const staged = el('div');
  if (!silent)
    clear(content, el('div', { class: 'loading', role: 'status' }, 'Loading…'));
  const scrollPositions = [
    ...content.querySelectorAll('.graph-viewport,.step-panel'),
  ].map((node) => ({ left: node.scrollLeft, top: node.scrollTop }));
  state.currentRun = null;
  const section =
    kind === 'tasks' || kind === 'attempts'
      ? 'executions'
      : kind === 'definitions'
        ? 'pipelines'
        : kind === 'compare'
          ? 'runs'
          : kind;
  [...navigation.children].forEach((node, index) => {
    const active = items[index][0] === section;
    node.classList.toggle('active', active);
    if (active) node.setAttribute('aria-current', 'page');
    else node.removeAttribute('aria-current');
  });
  try {
    if (!connected || silent || kind === 'service') await identify();
    if (kind === 'runs' && id === 'new') await runForm(staged, query, navigate);
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
    else if (kind === 'components' && id) await componentDetail(staged, id);
    else if (kind === 'artifacts' && id)
      await artifactDetail(staged, id, query, navigate, state);
    else if ((kind === 'tasks' || kind === 'attempts') && id)
      await executionDetail(staged, kind, id, navigate);
    else if (kind === 'compare') await compareRuns(staged, query);
    else if (kind === 'service') await serviceInfo(staged);
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
    clear(content, ...staged.childNodes);
    document.title =
      (content.querySelector('h1')?.textContent || 'Workspace') + ' · Dockflow';
    if (silent)
      [...content.querySelectorAll('.graph-viewport,.step-panel')].forEach(
        (node, index) => {
          if (scrollPositions[index]) {
            node.scrollLeft = scrollPositions[index].left;
            node.scrollTop = scrollPositions[index].top;
          }
        },
      );
    schedule();
  } catch (error) {
    if (
      turn !== generation ||
      error.name === 'AbortError' ||
      error.status === 401
    )
      return;
    if (silent) {
      content.querySelector('.refresh-error')?.remove();
      const warning = errorBox(error, () => render(true));
      warning.classList.add('refresh-error');
      content.prepend(warning);
      connection('Update failed · data may be stale', false);
    } else
      clear(
        content,
        errorBox(error, () => render()),
      );
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
