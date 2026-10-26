/** Names decorate references in place; identity, navigation and graph DOM stay intact. */
import { post } from './api.js';

const kinds = {
  run: 'runs',
  task: 'tasks',
  attempt: 'attempts',
  pipeline: 'pipelines',
  definition: 'definitions',
  component: 'components',
  experiment: 'experiments',
};
export function identity(value) {
  const match =
    /^(run|task|attempt|pipeline|definition|component|experiment)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.exec(
      value || '',
    );
  return match ? { collection: kinds[match[1]], id: value } : null;
}
export function referenceCaption(base, name, id, adjacentId = false) {
  const short = id.replace(/^[a-z]+_/, '').slice(0, 8);
  const hasId = adjacentId || base.includes(id) || base.includes(short);
  return [
    name ? (base.includes(name) ? null : name) : 'Name unavailable',
    base,
    hasId ? null : short,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function watchReferences(...roots) {
  let epoch = 0,
    timer,
    cache = new Map(),
    pending = new Map();
  let seen = new WeakMap(),
    originals = new WeakMap();
  const selector = 'a[href],option[value],input,span.id,[data-reference-id]';

  function reference(node) {
    if (node.dataset.filterAutocomplete) return null;
    let value;
    if (node.tagName === 'A') {
      const match =
        /^#\/(runs|tasks|attempts|pipelines|definitions|components|experiments)\/([^/?#]+)/.exec(
          node.getAttribute('href') || '',
        );
      if (!match) return null;
      try {
        value = decodeURIComponent(match[2]);
      } catch {
        return null;
      }
      const result = identity(value);
      return result?.collection === match[1] ? result : null;
    }
    if (node.tagName === 'OPTION' || node.tagName === 'INPUT')
      return identity(node.value);
    const result = identity(
      node.dataset.referenceId || node.textContent.trim(),
    );
    if (
      result &&
      (!node.dataset.referenceCollection ||
        result.collection === node.dataset.referenceCollection)
    ) {
      node.dataset.referenceId = result.id;
      node.dataset.referenceCollection = result.collection;
      return result;
    }
    return null;
  }
  function apply(node, item, name) {
    if (!node.isConnected) return;
    const current = reference(node);
    if (
      !current ||
      current.id !== item.id ||
      current.collection !== item.collection
    )
      return;
    if (node.tagName === 'INPUT') {
      let hint = node.parentElement.querySelector('.reference-input-name');
      if (!hint) {
        hint = document.createElement('small');
        hint.className = 'reference-input-name';
        hint.id = 'reference-name-' + crypto.randomUUID();
        node.before(hint);
      }
      const descriptions = new Set(
        (node.getAttribute('aria-describedby') || '')
          .split(' ')
          .filter(Boolean),
      );
      descriptions.add(hint.id);
      node.setAttribute('aria-describedby', [...descriptions].join(' '));
      hint.textContent = name || 'Name unavailable';
      hint.title = item.id;
      return;
    }
    if (!originals.has(node)) originals.set(node, node.textContent);
    const adjacentId =
      node.classList.contains('cell-main') &&
      Boolean(node.parentElement.querySelector('.cell-detail.id'));
    node.textContent = referenceCaption(
      originals.get(node),
      name,
      item.id,
      adjacentId,
    );
    node.title = [name, item.id].filter(Boolean).join(' · ');
    node.classList.add('resource-reference');
    node.dataset.referenceState = name ? 'named' : 'unavailable';
  }
  async function flush() {
    const turn = epoch;
    const queued = [...pending.values()].filter((item) => !item.sent);
    queued.forEach((item) => (item.sent = true));
    for (let start = 0; start < queued.length; start += 200) {
      const batch = queued.slice(start, start + 200);
      let items = [];
      try {
        const response = await post('/ui/reference-names', {
          references: batch.map(({ collection, id }) => ({ collection, id })),
        });
        items = Array.isArray(response.items) ? response.items : [];
      } catch (error) {
        if (error.name === 'AbortError' || turn !== epoch) return;
      }
      if (turn !== epoch) return;
      const names = new Map(
        items.map((item) => [
          item.collection + ':' + item.id,
          typeof item.name === 'string' && item.available ? item.name : null,
        ]),
      );
      for (const item of batch) {
        const key = item.collection + ':' + item.id;
        const name = names.get(key) || null;
        cache.set(key, name);
        pending.delete(key);
        for (const node of item.nodes) apply(node, item, name);
      }
    }
  }
  function scan() {
    for (const root of roots) {
      if (root.tagName === 'DIALOG' && !root.open) continue;
      for (const node of root.querySelectorAll(selector)) {
        const item = reference(node);
        if (!item) {
          if (node.tagName === 'INPUT') {
            node.parentElement.querySelector('.reference-input-name')?.remove();
            seen.delete(node);
          }
          continue;
        }
        const key = item.collection + ':' + item.id;
        if (seen.get(node) === epoch + ':' + key) continue;
        seen.set(node, epoch + ':' + key);
        if (cache.has(key)) apply(node, item, cache.get(key));
        else {
          if (!pending.has(key))
            pending.set(key, { ...item, nodes: new Set(), sent: false });
          pending.get(key).nodes.add(node);
        }
      }
    }
    if ([...pending.values()].some((item) => !item.sent)) {
      clearTimeout(timer);
      timer = setTimeout(flush, 0);
    }
  }
  const observer = new MutationObserver((records) => {
    if (
      records.some((record) =>
        [...record.addedNodes].some((node) => node.nodeType === 1),
      )
    )
      scan();
  });
  for (const root of roots) {
    observer.observe(root, { childList: true, subtree: true });
    root.addEventListener('change', scan);
  }
  return {
    scan,
    reset(forget = false) {
      epoch++;
      clearTimeout(timer);
      cache = new Map();
      pending = new Map();
      if (forget) {
        seen = new WeakMap();
        originals = new WeakMap();
      }
    },
  };
}
