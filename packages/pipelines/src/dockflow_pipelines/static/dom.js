/** Small DOM helpers. All resource content is inserted as text, never markup. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on') && typeof value === 'function')
      node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('aria-') && typeof value === 'boolean')
      node.setAttribute(key, String(value));
    else if (value !== undefined && value !== null && value !== false) {
      if (
        ['checked', 'disabled', 'required', 'multiple', 'selected'].includes(
          key,
        )
      )
        node[key] = Boolean(value);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
  }
  for (const child of children.flat(Infinity))
    if (child !== null && child !== undefined && child !== false)
      node.append(
        child instanceof Node ? child : document.createTextNode(String(child)),
      );
  return node;
}
export function clear(node, ...children) {
  node.replaceChildren(...children.filter(Boolean));
  return node;
}
export function button(label, action, style = 'secondary', attrs = {}) {
  return el(
    'button',
    { type: 'button', class: style, onClick: action, ...attrs },
    label,
  );
}
export function link(text, path, attrs = {}) {
  return el('a', { href: '#/' + path, ...attrs }, text);
}
export function referenceLabel(collection, id, compact = false) {
  return el(
    'span',
    {
      class: 'resource-reference',
      title: id,
      dataset: {
        referenceCollection: collection,
        referenceId: id,
      },
    },
    compact ? short(id) : id,
  );
}
export function json(value) {
  return el('pre', { class: 'code' }, JSON.stringify(value ?? null, null, 2));
}
export function short(id) {
  return id
    ? String(id)
        .replace(/^[a-z]+_/, '')
        .slice(0, 8)
    : '—';
}
export function date(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}
export function duration(record) {
  if (!record.started_at) return '—';
  const ms =
    (record.finished_at ? new Date(record.finished_at) : new Date()) -
    new Date(record.started_at);
  if (!Number.isFinite(ms)) return '—';
  const seconds = Math.max(0, ms / 1000);
  return seconds < 60
    ? `${seconds.toFixed(1)}s`
    : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}
export function badge(state = 'unknown') {
  return el(
    'span',
    { class: 'badge ' + String(state).replace(/[^a-z_-]/g, '') },
    el('span', { 'aria-hidden': 'true' }, '●'),
    state,
  );
}
export function empty(title, detail = '') {
  return el(
    'div',
    { class: 'empty' },
    el('span', { class: 'empty-symbol', 'aria-hidden': 'true' }, '◇'),
    el('h3', {}, title),
    el('p', {}, detail),
  );
}
export function notice(text, kind = 'info') {
  return el(
    'div',
    { class: 'notice ' + kind, role: kind === 'error' ? 'alert' : 'status' },
    text,
  );
}
export function errorBox(error, retry) {
  return el(
    'div',
    { class: 'notice error', role: 'alert' },
    el('strong', {}, error.code || 'Request failed'),
    el('p', {}, error.message || String(error)),
    error.requestId ? el('small', {}, 'Request ID: ' + error.requestId) : null,
    error.details?.length ? json(error.details) : null,
    retry ? button('Try again', retry) : null,
  );
}
export function table(headers, rows, message = 'No records found.') {
  return el(
    'div',
    { class: 'table-scroll' },
    el(
      'table',
      {},
      el(
        'thead',
        {},
        el(
          'tr',
          {},
          headers.map((h) => el('th', { scope: 'col' }, h)),
        ),
      ),
      el(
        'tbody',
        {},
        rows.length
          ? rows.map((row) =>
              el(
                'tr',
                {},
                row.map((cell) => el('td', {}, cell ?? '—')),
              ),
            )
          : el(
              'tr',
              { class: 'empty-row' },
              el(
                'td',
                { colspan: headers.length },
                empty(message, 'Records appear here after they are created.'),
              ),
            ),
      ),
    ),
  );
}

export function listScreen(header, content, footer, label = 'Records') {
  return el(
    'section',
    { class: 'list-screen' },
    el('header', { class: 'list-header' }, header),
    el(
      'div',
      {
        class: 'list-content',
        role: 'region',
        tabindex: '0',
        'aria-label': label,
      },
      content,
    ),
    el('footer', { class: 'list-footer' }, footer),
  );
}

/** Bounded, already-loaded detail/comparison rows; never claims a server total. */
export function localList(
  headers,
  rows,
  { title = 'Records', header, limited = false } = {},
) {
  const content = el('div'),
    footer = el('div', { class: 'pager' });
  const screen = listScreen(
    header || el('h2', {}, title),
    content,
    footer,
    title,
  );
  let page = 0;
  function render() {
    const start = page * 50,
      visible = rows.slice(start, start + 50);
    clear(content, table(headers, visible));
    clear(
      footer,
      el(
        'span',
        {},
        `${visible.length} rows on page ${page + 1} · ${rows.length} loaded${limited ? ' · truncated subset' : ''}`,
      ),
      el(
        'div',
        { class: 'actions' },
        button(
          'Previous',
          () => {
            page--;
            render();
          },
          'secondary',
          { disabled: page === 0 },
        ),
        button(
          'Next',
          () => {
            page++;
            render();
          },
          'secondary',
          { disabled: start + 50 >= rows.length },
        ),
      ),
    );
    screen.querySelector('.list-content').scrollTop = 0;
  }
  screen.capturePage = () => page;
  screen.restorePage = (saved) => {
    if (!Number.isInteger(saved)) return;
    page = Math.max(0, Math.min(saved, Math.ceil(rows.length / 50) - 1));
    render();
  };
  render();
  return screen;
}
export function fields(items) {
  return el(
    'dl',
    { class: 'details-grid' },
    items.flatMap(([key, value]) => [
      el('dt', {}, key),
      el('dd', {}, value ?? '—'),
    ]),
  );
}
export function tabs(names, selected, onChange) {
  return el(
    'div',
    { class: 'tabs', role: 'tablist' },
    names.map((name) =>
      button(name, () => onChange(name), 'tab', {
        role: 'tab',
        'aria-selected': name === selected,
      }),
    ),
  );
}
export function section(title, ...content) {
  return el('section', { class: 'panel' }, el('h2', {}, title), ...content);
}
export function pageHeader(title, subtitle, actions = []) {
  return el(
    'div',
    { class: 'page-heading' },
    el(
      'div',
      {},
      el('h1', { title }, title),
      subtitle ? el('p', { class: 'subtle' }, subtitle) : null,
    ),
    el('div', { class: 'actions' }, actions),
  );
}
export function download(name, text, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el('a', { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function toast(text) {
  const node = document.getElementById('toast');
  if (!node) return;
  node.textContent = text;
  node.classList.add('visible');
  setTimeout(() => node.classList.remove('visible'), 4000);
}
export function modal(title, content) {
  const dialog = document.getElementById('modal');
  const previous = document.activeElement;
  if (dialog.open) dialog.close();
  delete dialog.dataset.kind;
  clear(
    dialog,
    el(
      'div',
      { class: 'dialog-header' },
      el('h2', { id: 'dialog-title' }, title),
      button('×', () => dialog.close(), 'icon-button', {
        'aria-label': 'Close dialog',
      }),
    ),
    content,
  );
  dialog.addEventListener(
    'close',
    () => previous?.isConnected && previous.focus(),
    { once: true },
  );
  dialog.showModal();
  return dialog;
}
export function labeled(text, control, hint) {
  const id = control.id || 'field-' + crypto.randomUUID();
  control.id = id;
  return el(
    'div',
    { class: 'field' },
    el('label', { for: id }, text),
    control,
    hint ? el('small', { class: 'subtle' }, hint) : null,
  );
}
export async function busy(control, action) {
  control.disabled = true;
  try {
    return await action();
  } finally {
    control.disabled = false;
  }
}
