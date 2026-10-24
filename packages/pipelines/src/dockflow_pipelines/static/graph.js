/** KFP compiled graph projection; never evaluates component code or conditions. */
import { el, button, badge, notice, empty, clear } from './dom.js';
export function graphModel(spec) {
  const document = spec.pipelineSpec || spec;
  const nodes = [];
  const edges = [];
  function visit(component, prefix = '', parent = null, seen = new Set()) {
    for (const [key, task] of Object.entries(component.dag?.tasks || {})) {
      const name = prefix + key,
        componentKey = task.componentRef?.name,
        child = document.components?.[componentKey] || {};
      nodes.push({
        name,
        label: task.taskInfo?.name || key,
        componentKey,
        component: child,
        task,
        parent,
        group: Boolean(child.dag),
      });
      const dependencies = new Set(task.dependentTasks || []);
      for (const kind of Object.values(task.inputs || {}))
        for (const source of Object.values(kind)) {
          for (const binding of Object.values(source))
            if (binding && typeof binding === 'object' && binding.producerTask)
              dependencies.add(binding.producerTask);
        }
      for (const dependency of dependencies)
        edges.push({ from: prefix + dependency, to: name, kind: 'dependency' });
      if (parent) edges.push({ from: parent, to: name, kind: 'containment' });
      if (child.dag && !seen.has(componentKey))
        visit(child, name + '/', name, new Set([...seen, componentKey]));
    }
  }
  visit(document.root || {});
  if (!nodes.length && document.root?.executorLabel)
    nodes.push({
      name: 'root',
      label: document.pipelineInfo?.name || 'root',
      componentKey: 'root',
      component: document.root,
      task: {},
      parent: null,
      group: false,
    });
  return { nodes, edges };
}
/** Select one DAG level without changing native task paths or dependencies. */
export function graphView(model, { path, selected, all = false } = {}) {
  const byName = new Map(model.nodes.map((node) => [node.name, node]));
  const requested = path === undefined ? byName.get(selected)?.parent : path;
  const scope = byName.get(requested)?.group ? requested : null;
  const nodes = all
    ? model.nodes
    : model.nodes.filter((node) => node.parent === scope);
  const ids = new Set(nodes.map((node) => node.name));
  const ancestors = [];
  for (
    let current = byName.get(scope);
    current;
    current = byName.get(current.parent)
  )
    ancestors.unshift(current);
  return {
    nodes,
    edges: model.edges.filter((edge) => ids.has(edge.from) && ids.has(edge.to)),
    path: scope,
    ancestors,
    all,
    invalidPath: Boolean(requested && requested !== scope),
  };
}

export function graph(
  spec,
  tasks = [],
  selected,
  onSelect = () => {},
  options = {},
) {
  const model = graphModel(spec);
  if (!model.nodes.length) return empty('No tasks in this definition.');
  const host = el('div', { class: 'graph' });
  function render(path = options.path, all = options.all) {
    const view = graphView(model, { path, selected, all });
    const nodes = view.nodes.slice(0, 1000);
    const ids = new Set(nodes.map((n) => n.name));
    const edges = view.edges.filter((e) => ids.has(e.from) && ids.has(e.to));
    function navigate(path, all = false) {
      if (options.onNavigate) options.onNavigate({ path: path || '', all });
      else render(path || '', all);
    }
    const levels = new Map();
    const pending = new Set(ids);
    while (pending.size) {
      let progress = false;
      for (const id of pending) {
        const parents = edges.filter((e) => e.to === id).map((e) => e.from);
        if (parents.every((p) => levels.has(p))) {
          levels.set(
            id,
            parents.length
              ? 1 + Math.max(...parents.map((p) => levels.get(p)))
              : 0,
          );
          pending.delete(id);
          progress = true;
        }
      }
      if (!progress) {
        for (const id of pending) levels.set(id, 0);
        break;
      }
    }
    const rows = new Map();
    const positions = new Map();
    for (const node of nodes) {
      const level = levels.get(node.name),
        row = rows.get(level) || 0;
      rows.set(level, row + 1);
      positions.set(node.name, { x: 32 + level * 280, y: 32 + row * 144 });
    }
    const width = 70 + (Math.max(0, ...levels.values()) + 1) * 280,
      height = Math.max(260, 60 + Math.max(0, ...rows.values()) * 144);
    const surface = el('div', { class: 'graph-surface' });
    surface.style.width = width + 'px';
    surface.style.height = height + 'px';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('graph-edges');
    for (const edge of edges) {
      const start = positions.get(edge.from),
        end = positions.get(edge.to);
      const path = document.createElementNS(svg.namespaceURI, 'path');
      path.setAttribute(
        'd',
        `M ${start.x + 230} ${start.y + 48} C ${start.x + 255} ${start.y + 48}, ${end.x - 25} ${end.y + 48}, ${end.x} ${end.y + 48}`,
      );
      path.setAttribute('class', edge.kind);
      svg.append(path);
    }
    surface.append(svg);
    const actual = new Map(tasks.map((t) => [t.name, t]));
    for (const node of nodes) {
      const record = actual.get(node.name);
      const pos = positions.get(node.name);
      const state = record?.state || 'not_started';
      const descendants = node.group
        ? model.nodes.filter((child) => child.name.startsWith(node.name + '/'))
        : [];
      const counts = new Map();
      for (const child of descendants) {
        const state = actual.get(child.name)?.state;
        if (state && state !== 'succeeded')
          counts.set(state, (counts.get(state) || 0) + 1);
      }
      const summary = node.group
        ? `${descendants.length} nested ${descendants.length === 1 ? 'task' : 'tasks'}` +
          [...counts].map(([state, count]) => ` · ${count} ${state}`).join('')
        : '';
      const control = el('div', {
        class:
          'graph-node ' +
          (node.group ? 'group ' : '') +
          (selected === node.name ? 'selected' : ''),
        dataset: { node: node.name },
      });
      const select = button(
        '',
        () => onSelect(node.name),
        'graph-node-select',
        {
          'aria-label': `${node.name}: ${record?.state || 'not started'}${summary ? '. ' + summary : ''}`,
          'aria-pressed': selected === node.name,
          title: node.name,
        },
      );
      control.style.left = pos.x + 'px';
      control.style.top = pos.y + 'px';
      select.append(
        el('strong', {}, node.label),
        el(
          'small',
          { class: 'subtle' },
          node.parent ? node.name : node.componentKey,
        ),
        record
          ? badge(state)
          : el(
              'span',
              { class: 'subtle' },
              node.group
                ? 'Subpipeline'
                : node.task.triggerPolicy?.condition
                  ? 'Conditional step'
                  : 'Component',
            ),
      );
      if (summary)
        select.append(
          el('small', { class: 'subtle', title: summary }, summary),
        );
      control.append(select);
      if (node.group)
        control.append(
          button(
            'Open subpipeline ›',
            () => navigate(node.name),
            'graph-open',
            {
              'aria-label': 'Open subpipeline ' + node.name,
            },
          ),
        );
      surface.append(control);
    }
    const canvas = el('div', { class: 'graph-canvas' }, surface),
      viewport = el(
        'div',
        {
          class: 'graph-viewport',
          tabindex: '0',
          'aria-label': 'Pipeline graph. Scroll to pan.',
        },
        canvas,
      );
    let zoom = 1;
    const zoomText = el('span', { class: 'subtle' }, '100%');
    function scale(value) {
      zoom = Math.max(0.3, Math.min(1.5, value));
      surface.style.transform = `scale(${zoom})`;
      canvas.style.width = width * zoom + 'px';
      canvas.style.height = height * zoom + 'px';
      zoomText.textContent = Math.round(zoom * 100) + '%';
    }
    scale(1);
    const breadcrumb = el(
      'nav',
      { class: 'graph-breadcrumb', 'aria-label': 'Graph location' },
      button('Pipeline', () => navigate(''), 'quiet', {
        'aria-current': !view.path && !view.all ? 'location' : null,
      }),
      view.all
        ? el('span', { 'aria-current': 'location' }, ' / All tasks')
        : view.ancestors.map((ancestor, index) => [
            el('span', { 'aria-hidden': 'true' }, ' / '),
            button(ancestor.label, () => navigate(ancestor.name), 'quiet', {
              title: ancestor.name,
              'aria-current':
                index === view.ancestors.length - 1 ? 'location' : null,
            }),
          ]),
    );
    clear(
      host,
      breadcrumb,
      el(
        'div',
        { class: 'graph-toolbar' },
        el(
          'span',
          { class: 'subtle' },
          `${nodes.length} visible nodes · ${model.nodes.length} total tasks` +
            (view.all
              ? ' · solid: dependency · dotted: containment'
              : ' · subpipelines collapsed'),
        ),
        el(
          'div',
          { class: 'actions' },
          button(
            view.all ? 'Grouped view' : 'All tasks',
            () => navigate(view.path, !view.all),
            'quiet',
          ),
          button('−', () => scale(zoom - 0.1), 'icon-button', {
            'aria-label': 'Zoom out',
          }),
          zoomText,
          button('+', () => scale(zoom + 0.1), 'icon-button', {
            'aria-label': 'Zoom in',
          }),
          button('Reset', () => scale(1), 'quiet'),
        ),
      ),
      view.invalidPath
        ? notice(
            'Subpipeline not found in this definition. Showing the pipeline level.',
          )
        : null,
      view.nodes.length > 1000
        ? notice(
            'Showing the first 1,000 graph nodes. Inspect the source for the complete definition.',
          )
        : null,
      view.nodes.length ? viewport : empty('No tasks in this subpipeline.'),
    );
  }
  render();
  return host;
}
