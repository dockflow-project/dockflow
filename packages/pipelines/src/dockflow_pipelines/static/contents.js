/** Bounded artifact previews. Payload strings become text nodes, never markup. */
import {
  el,
  button,
  link,
  table,
  notice,
  errorBox,
  listScreen,
  labeled,
  clear,
} from './dom.js';
import { get } from './api.js';
import { bytes } from './cleanup.js';

export function jsonTree(root, saved = { open: new Map(), loaded: new Map() }) {
  function node(value, key, array = false, address = 'root') {
    const open = saved.open.get(address) ?? address === 'root';
    const label =
      key === undefined
        ? []
        : [el('span', { class: 'json-key' }, array ? `[${key}]` : key), ': '];
    if (!value.children)
      return el(
        'div',
        { class: 'json-leaf' },
        label,
        el(
          'span',
          { class: 'json-' + value.kind },
          value.kind === 'null' ? 'null' : String(value.value),
        ),
      );
    const children = el('div', { class: 'json-children' });
    const details = el(
      'details',
      { class: 'json-branch', open },
      el(
        'summary',
        {},
        label,
        value.kind === 'array' ? '[…]' : '{…}',
        el(
          'small',
          { class: 'subtle' },
          ` ${value.children.length} ${value.kind === 'array' ? 'items' : 'properties'}`,
        ),
      ),
      children,
    );
    let loaded = 0;
    const more = button('Show next 100', fill);
    function fill() {
      more.remove();
      const end = Math.min(loaded + 100, value.children.length);
      for (; loaded < end; loaded++) {
        const child = value.children[loaded];
        children.append(
          node(
            child.node,
            child.key,
            value.kind === 'array',
            address + '.' + loaded,
          ),
        );
      }
      saved.loaded.set(address, loaded);
      if (loaded < value.children.length) children.append(more);
    }
    function expand() {
      const count = Math.max(100, saved.loaded.get(address) || 0);
      do {
        fill();
      } while (loaded < Math.min(count, value.children.length));
    }
    details.addEventListener('toggle', () => {
      saved.open.set(address, details.open);
      if (details.open && !loaded) expand();
    });
    if (open) expand();
    return details;
  }
  return el('div', { class: 'json-tree' }, node(root));
}

export async function artifactContents(artifact, query, navigate, state) {
  const route = 'artifacts/' + artifact.artifact_id;
  const path = query.get('path') || '',
    preview = query.get('preview') || 'auto';
  const token = query.get('content_page');
  function parameters(nextPath = path, format = preview, page = null) {
    const next = new URLSearchParams({ tab: 'Contents' });
    if (nextPath) next.set('path', nextPath);
    if (format !== 'auto') next.set('preview', format);
    if (page) next.set('content_page', page);
    return next;
  }
  const crumbs = el(
    'div',
    { class: 'contents-breadcrumb', 'aria-label': 'Artifact path' },
    link('Artifact root', route + '?' + parameters('', 'auto')),
  );
  const parts = path.split('/').filter(Boolean);
  parts.forEach((part, index) =>
    crumbs.append(
      ' / ',
      link(
        part,
        route + '?' + parameters(parts.slice(0, index + 1).join('/'), 'auto'),
      ),
    ),
  );
  const format = el(
    'select',
    {
      'aria-label': 'Preview format',
      onChange: (event) =>
        navigate(route, parameters(path, event.target.value)),
    },
    ['auto', 'csv', 'json', 'image', 'text'].map((value) =>
      el(
        'option',
        { value, selected: value === preview },
        value === 'auto' ? 'Automatic' : value.toUpperCase(),
      ),
    ),
  );
  const header = el(
    'div',
    {},
    crumbs,
    el('div', { class: 'toolbar' }, labeled('View as', format)),
  );
  let data;
  try {
    data = await get('/artifacts/' + artifact.artifact_id + '/contents', {
      path,
      format: preview,
      page_token: token,
    });
  } catch (error) {
    if (error.name === 'AbortError' || error.status === 401) throw error;
    return listScreen(
      header,
      el(
        'div',
        { class: 'contents-padding' },
        errorBox(error, () => navigate(route, query, true)),
        notice(
          'Overview and Lineage remain available. A text preview can inspect the beginning of a large UTF-8 file.',
        ),
        button('Start from beginning', () => navigate(route, parameters())),
      ),
      el('div', { class: 'pager' }, 'Contents unavailable'),
      'Artifact contents',
    );
  }
  const description = el(
    'span',
    {},
    `${data.format.toUpperCase()}${data.name ? ' · ' + data.name : ''} · ${bytes(data.size_bytes)}`,
  );
  const footer = el(
    'div',
    {},
    el(
      'div',
      { class: 'contents-status' },
      description,
      el('small', { class: 'subtle' }, data.message),
    ),
  );
  let content;
  if (data.format === 'directory') {
    format.closest('.toolbar').remove();
    content = table(
      ['Name', 'Kind', 'Size'],
      data.items.map((item) => [
        link(
          (item.kind === 'directory' ? '▸ ' : '') + item.name,
          route + '?' + parameters(item.path, 'auto'),
        ),
        item.kind,
        item.kind === 'file' ? bytes(item.size_bytes) : '—',
      ]),
      'This directory is empty.',
    );
  } else if (data.format === 'csv') {
    const width = Math.max(
      data.columns.length,
      ...data.rows.map((row) => row.length),
    );
    const headings = Array.from(
      { length: width },
      (_, i) => data.columns[i] ?? `Column ${i + 1}`,
    );
    content = table(
      headings.length ? headings : ['CSV'],
      data.rows.map((row) => headings.map((_, i) => row[i] ?? '—')),
      'No CSV data rows.',
    );
    content.classList.add('csv-preview');
    header.append(
      el(
        'small',
        { class: 'subtle' },
        'First record supplies column headings. Values are displayed as text.',
      ),
    );
  } else if (data.format === 'json') {
    const key = JSON.stringify([
      artifact.artifact_id,
      artifact.fingerprint,
      path,
    ]);
    state.contentsTrees ||= new Map();
    if (!state.contentsTrees.has(key))
      state.contentsTrees.set(key, { open: new Map(), loaded: new Map() });
    content = el(
      'div',
      { class: 'contents-padding' },
      jsonTree(data.tree, state.contentsTrees.get(key)),
    );
    header.append(
      el(
        'small',
        { class: 'subtle' },
        'Expand a branch to inspect its values. Large branches show 100 entries at a time.',
      ),
    );
  } else if (data.format === 'image') {
    const supported = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
    if (!supported.includes(data.mime_type))
      throw new Error('Unsupported image response');
    const image = el('img', {
      src: `data:${data.mime_type};base64,${data.base64}`,
      alt: data.name || 'Artifact image',
      decoding: 'async',
    });
    const figure = el('figure', { class: 'artifact-image' }, image);
    image.addEventListener('error', () =>
      clear(
        figure,
        notice('The browser could not decode this image.', 'error'),
      ),
    );
    const fit = button('Actual size', () => {
      const natural = image.classList.toggle('natural-size');
      fit.textContent = natural ? 'Fit to width' : 'Actual size';
    });
    header.append(
      el(
        'div',
        { class: 'actions' },
        fit,
        el('span', { class: 'subtle' }, `${data.width} × ${data.height}`),
      ),
    );
    content = figure;
  } else if (data.format === 'text') {
    content = el(
      'div',
      { class: 'contents-padding' },
      data.truncated
        ? notice(
            'Showing only the first 64 KiB of UTF-8 text. This is not the complete file.',
          )
        : null,
      el('pre', { class: 'code artifact-text' }, data.text),
    );
  } else
    content = el('div', { class: 'contents-padding' }, notice(data.message));
  if (['csv', 'directory'].includes(data.format)) {
    const key = JSON.stringify([
      'contents',
      artifact.artifact_id,
      path,
      preview,
    ]);
    const history = (state.pages[key] ||= new Map());
    const previousKnown = !token || history.has(token);
    footer.append(
      el(
        'div',
        { class: 'pager' },
        el(
          'span',
          {},
          data.format === 'csv'
            ? `${data.rows.length} rows · ${data.first_row}–${data.last_row}${data.next_page_token ? ' · more available' : ' · end of file'}`
            : `${data.items.length} entries on this page · ${data.total_entries} in this directory`,
        ),
        el(
          'div',
          { class: 'actions' },
          button(
            previousKnown ? 'Previous' : 'First page',
            () =>
              navigate(route, parameters(path, preview, history.get(token))),
            'secondary',
            { disabled: !token },
          ),
          button(
            'Next',
            () => {
              history.set(data.next_page_token, token || '');
              navigate(route, parameters(path, preview, data.next_page_token));
            },
            'secondary',
            { disabled: !data.next_page_token },
          ),
        ),
      ),
    );
  }
  return listScreen(header, content, footer, 'Artifact contents');
}
