/** Recent, server-filtered options; exact filter values stay in the input. */
import { el, clear } from './dom.js';
import { get, signal } from './api.js';

export function filterValue(input) {
  return input.dataset.selectedCaption === input.value
    ? input.dataset.selectedValue
    : input.value;
}

export function autocomplete(
  input,
  collection,
  field = null,
  scope = () => ({}),
) {
  const id = 'filter-options-' + crypto.randomUUID();
  const list = el('div', {
    id,
    class: 'autocomplete-options',
    role: 'listbox',
    hidden: true,
    'aria-label': 'Filter suggestions',
  });
  const clearSelection = el(
    'button',
    {
      type: 'button',
      class: 'autocomplete-clear',
      hidden: true,
      'aria-label':
        'Clear ' +
        (input.labels?.[0]?.textContent ||
          input.parentElement?.querySelector('label')?.textContent ||
          'selection'),
      title: 'Clear selection',
      onClick: () => {
        input.autocompleteControl.clear();
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.focus();
      },
    },
    '×',
  );
  const wrapper = el(
    'div',
    { class: 'autocomplete' },
    input,
    clearSelection,
    list,
  );
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', id);
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('autocomplete', 'off');
  input.dataset.filterAutocomplete = 'true';
  input.setAttribute('maxlength', '256');
  let epoch = 0,
    timer,
    items = [],
    active = -1;
  const pageSignal = signal();
  function forgetSelection() {
    clearSelection.hidden = true;
    delete input.dataset.selectedValue;
    delete input.dataset.selectedCaption;
  }
  function display(item) {
    const caption =
      item.name && item.name !== item.id
        ? item.name + ' · ' + item.id
        : item.value;
    input.value = caption;
    input.setSelectionRange(0, 0);
    input.scrollLeft = 0;
    input.dataset.selectedCaption = caption;
    input.dataset.selectedValue = item.value;
    input.title = caption;
    clearSelection.hidden = false;
  }
  function close() {
    epoch++;
    clearTimeout(timer);
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }
  function position() {
    const rect = input.getBoundingClientRect();
    const below = innerHeight - rect.bottom - 8;
    const minimumLeft = Math.max(
      4,
      document.querySelector('.workspace')?.getBoundingClientRect().left || 4,
    );
    const width = Math.min(
      Math.max(rect.width, 300),
      innerWidth - minimumLeft - 8,
    );
    const above = below < 140 && rect.top > below;
    const height = Math.max(60, Math.min(320, above ? rect.top - 8 : below));
    Object.assign(list.style, {
      left:
        Math.max(minimumLeft, Math.min(rect.left, innerWidth - width - 4)) +
        'px',
      width: width + 'px',
      maxHeight: height + 'px',
      top: above ? 'auto' : rect.bottom + 4 + 'px',
      bottom: above ? innerHeight - rect.top + 4 + 'px' : 'auto',
    });
  }
  function open() {
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    position();
  }
  function select(index) {
    const item = items[index];
    if (!item) return;
    display(item);
    close();
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function highlight(index) {
    active = index;
    [...list.querySelectorAll('[role=option]')].forEach((option, i) => {
      option.setAttribute('aria-selected', String(i === active));
      if (i === active) {
        input.setAttribute('aria-activedescendant', option.id);
        option.scrollIntoView({ block: 'nearest' });
      }
    });
  }
  async function load() {
    const turn = ++epoch;
    active = -1;
    items = [];
    input.removeAttribute('aria-activedescendant');
    clear(
      list,
      el('div', { class: 'autocomplete-message', role: 'status' }, 'Loading…'),
    );
    open();
    try {
      const response = await get('/ui/filter-options', {
        collection,
        search: filterValue(input),
        field,
        ...scope(),
      });
      if (
        turn !== epoch ||
        !input.isConnected ||
        document.activeElement !== input ||
        pageSignal.aborted
      )
        return;
      items = response.items.slice(0, 10);
      clear(
        list,
        ...items.map((item, i) =>
          el(
            'div',
            {
              role: 'option',
              id: id + '-' + i,
              'aria-selected': 'false',
              class: 'autocomplete-option',
              onMousedown: (event) => event.preventDefault(),
              onClick: () => select(i),
            },
            el('strong', {}, item.name || item.id),
            item.name && item.id !== item.name
              ? el('small', {}, item.id)
              : null,
          ),
        ),
      );
      if (!items.length)
        list.append(
          el(
            'div',
            { class: 'autocomplete-message', role: 'status' },
            'No matching options',
          ),
        );
      if (response.remaining_count > 0)
        list.append(
          el(
            'div',
            { class: 'autocomplete-more', role: 'status' },
            '...and ' + response.remaining_count + ' more',
          ),
        );
    } catch (error) {
      if (
        turn !== epoch ||
        error.name === 'AbortError' ||
        pageSignal.aborted ||
        !input.isConnected
      )
        return;
      clear(
        list,
        el(
          'div',
          { class: 'autocomplete-message', role: 'status' },
          'Suggestions unavailable. You can still enter a filter.',
        ),
      );
    }
  }
  input.addEventListener('focus', load);
  input.addEventListener('click', () => {
    if (list.hidden) load();
  });
  input.addEventListener('blur', close);
  input.addEventListener('input', () => {
    forgetSelection();
    close();
    input.removeAttribute('title');
    timer = setTimeout(load, 180);
  });
  input.autocompleteControl = {
    clear() {
      close();
      forgetSelection();
      input.value = '';
      input.removeAttribute('title');
    },
  };
  const initial = input.value;
  const initialTurn = epoch;
  if (initial)
    get('/ui/filter-options', {
      collection,
      search: initial,
      field,
      ...scope(),
    })
      .then((response) => {
        if (
          pageSignal.aborted ||
          epoch !== initialTurn ||
          !input.isConnected ||
          input.value !== initial
        )
          return;
        const item = response.items.find((item) => item.value === initial);
        if (item) display(item);
      })
      .catch(() => {});
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (!list.hidden) event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (list.hidden) load();
      else if (items.length)
        highlight(
          active < 0
            ? event.key === 'ArrowDown'
              ? 0
              : items.length - 1
            : (active + (event.key === 'ArrowDown' ? 1 : -1) + items.length) %
                items.length,
        );
    } else if (event.key === 'Enter' && !list.hidden && active >= 0) {
      event.preventDefault();
      select(active);
    }
  });
  pageSignal.addEventListener('abort', close, { once: true });
  window.addEventListener('resize', close, { signal: pageSignal });
  document.addEventListener(
    'scroll',
    (event) => {
      if (!list.hidden && !list.contains(event.target)) close();
    },
    { capture: true, signal: pageSignal },
  );
  return wrapper;
}
