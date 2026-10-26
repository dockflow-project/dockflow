/** Reviewed deletion plans shared by record dialogs and managed storage cleanup. */
import {
  el,
  clear,
  button,
  link,
  json,
  notice,
  errorBox,
  table,
  pageHeader,
  labeled,
  modal,
  fields,
  listScreen,
  referenceLabel,
} from './dom.js';
import { post } from './api.js';
import { autocomplete, filterValue } from './autocomplete.js';

export function removeSelection(selected, rowId, groups = {}) {
  const removed = new Set([rowId]);
  let size;
  do {
    size = removed.size;
    for (const members of Object.values(groups))
      if (members.some((id) => removed.has(id)))
        for (const id of members) removed.add(id);
  } while (removed.size !== size);
  return selected.filter((id) => !removed.has(id));
}

export function bytes(value) {
  if (value === null || value === undefined) return 'Unknown';
  if (value < 1024) return `${value} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let amount = value / 1024,
    index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index++;
  }
  return `${amount.toFixed(2)} ${units[index]}`;
}

export function reviewPlan(plan, after) {
  const errors = el('div');
  const confirmation = el('input', {
    autocomplete: 'off',
    placeholder: 'DANGER',
    'aria-label': 'Type DANGER',
  });
  const submit = el(
    'button',
    {
      type: 'submit',
      class: 'danger',
      disabled: Boolean(plan.blockers.length) || plan.delete_files,
    },
    plan.state === 'partial'
      ? 'Retry remaining files'
      : 'Delete reviewed selection',
  );
  const summary = fields([
    ['Storage location', plan.location],
    ['Plan', plan.plan_id],
    ['Resource records', plan.targets.length],
    ['Files / objects', plan.rows.length],
    ['Estimated removable bytes', bytes(plan.estimated_bytes)],
  ]);
  const form = el(
    'form',
    {},
    summary,
    plan.targets.length
      ? el(
          'ul',
          { class: 'review-targets' },
          plan.targets.map((target) =>
            el('li', {}, referenceLabel(target.collection, target.id)),
          ),
        )
      : null,
    plan.blockers.length
      ? notice(plan.blockers.join('\n'), 'error')
      : notice(
          'This operation cannot be undone. Deletion will recheck references and file identities.',
        ),
    plan.rows.length
      ? el(
          'details',
          {},
          el('summary', {}, 'Exact file selection'),
          json(
            plan.rows.map((row) => ({
              path: row.path,
              size_bytes: row.size_bytes,
              artifacts: row.artifact_ids,
            })),
          ),
        )
      : null,
    plan.delete_files
      ? labeled('Type DANGER to confirm storage deletion', confirmation)
      : notice(
          'Storage files will be kept. Record deletion does not reclaim database journal space.',
        ),
    errors,
    el('div', { class: 'actions' }, submit),
  );
  const dialog = modal('Review deletion', form);
  confirmation.addEventListener('input', () => {
    submit.disabled =
      Boolean(plan.blockers.length) || confirmation.value !== 'DANGER';
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const result = await post('/deletions/apply', {
        plan_id: plan.plan_id,
        confirmation: confirmation.value,
      });
      if (result.state !== 'completed') {
        clear(
          errors,
          notice(
            'Deletion is incomplete. Completed files will not be replayed. Inspect the failures and retry this same plan.',
            'error',
          ),
          json(result.failures),
        );
        submit.textContent = 'Retry remaining files';
      } else {
        dialog.close();
        await after?.(result);
      }
    } catch (error) {
      clear(errors, errorBox(error));
    } finally {
      submit.disabled =
        Boolean(plan.blockers.length) ||
        (plan.delete_files && confirmation.value !== 'DANGER');
    }
  });
  if (plan.delete_files) confirmation.focus();
}

export function deleteResource(collection, id, after) {
  const files = el('input', { type: 'checkbox' });
  const errors = el('div');
  const submit = el(
    'button',
    { type: 'submit', class: 'danger' },
    'Review deletion',
  );
  const form = el(
    'form',
    {},
    referenceLabel(collection, id),
    notice(
      collection === 'artifacts'
        ? 'The artifact record and its files share the same dependency protections. Needed or pinned artifacts cannot be deleted.'
        : 'Only terminal, reconciled records can be deleted. Registered artifacts remain independent; retained execution selections block deletion.',
    ),
    collection === 'artifacts'
      ? labeled(
          'Also delete managed storage files',
          files,
          'External source files are never deleted. Directory artifacts are deleted as a whole.',
        )
      : null,
    errors,
    el('div', { class: 'actions' }, submit),
  );
  modal(
    'Delete ' +
      (collection === 'attempts' ? 'execution' : collection.slice(0, -1)),
    form,
  );
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const plan = await post('/deletions/plan', {
        targets: [{ collection, id }],
        delete_files: collection === 'artifacts' && files.checked,
      });
      reviewPlan(plan, after);
    } catch (error) {
      clear(errors, errorBox(error));
      submit.disabled = false;
    }
  });
}

const classes = [
  'execution_artifact',
  'manual_artifact',
  'publication',
  'retained_file',
  'orphan',
  'protected',
  'unknown',
];

function showClassificationHelp() {
  modal(
    'Storage classifications',
    el(
      'div',
      { class: 'dialog-body' },
      el(
        'dl',
        { class: 'classification-help' },
        [
          [
            'Execution artifact',
            'Files registered as an artifact produced by an execution. Deletion is allowed only when no retained references, pins or other protections need the artifact.',
          ],
          [
            'Manual artifact',
            'Files registered or imported manually, such as a database snapshot. They require explicit artifact deletion and are excluded from orphan cleanup and automatic retention.',
          ],
          [
            'Publication',
            'Files covered by a publication claim or manifest, even without a producing run. These ownership records protect the files from orphan cleanup.',
          ],
          [
            'Retained file',
            'Files deliberately kept when an eligible artifact record was deleted. Select them explicitly to delete them; orphan cleanup and automatic retention exclude them.',
          ],
          [
            'Orphan',
            'Files with no artifact, retained-file or publication ownership found in a complete scan. Eligible orphans can be selected individually or with “Select all eligible orphans”.',
          ],
          [
            'Protected',
            'Files that cannot be safely deleted, such as Dockflow system metadata, active work or files with unresolved ownership. The row shows the reason.',
          ],
          [
            'Unknown',
            'Entries whose ownership or file type cannot be safely determined. They are excluded from deletion.',
          ],
        ].map(([name, description]) => [
          el('dt', {}, name),
          el('dd', {}, description),
        ]),
      ),
      notice(
        'A classification describes ownership. Always check the row’s deletion blockers. Every storage deletion requires typing DANGER.',
      ),
    ),
  );
}

export async function storageCleanup(container, state) {
  state.cleanup ||= {
    scanId: null,
    selected: [],
    page: null,
    history: [],
    classification: '',
    artifactId: '',
  };
  const view = state.cleanup;
  const errors = el('div'),
    results = el('div'),
    counters = el('div', { class: 'cleanup-totals', 'aria-live': 'polite' });
  const pagination = el('div', { class: 'pager' }),
    location = el('div'),
    jobErrors = el('div');
  const prefix = el('input', {
    placeholder: 'Optional relative directory/prefix',
    value: view.prefix || '',
  });
  const classification = el(
    'select',
    {},
    el('option', { value: '' }, 'All classifications'),
    classes.map((value) =>
      el(
        'option',
        { value, selected: value === view.classification },
        value.replaceAll('_', ' '),
      ),
    ),
  );
  const artifactId = el('input', {
    value: view.artifactId,
    placeholder: 'Search artifact name or ID',
  });
  const artifactFilter = labeled('Artifact', artifactId);
  artifactFilter.append(autocomplete(artifactId, 'artifacts'));
  const scan = button(
    view.scanId ? 'Rescan storage' : 'Scan storage',
    async () => {
      scan.disabled = true;
      clear(errors);
      clear(
        scanStatus,
        notice(
          'Scanning the complete storage scope. Totals become available after the listing completes.',
        ),
      );
      try {
        const data = await post('/storage/scan', { prefix: prefix.value });
        view.scanId = data.scan_id;
        view.prefix = prefix.value;
        view.selected = [];
        view.page = null;
        view.history = [];
        await refresh(true);
      } catch (error) {
        clear(errors, errorBox(error));
      } finally {
        clear(scanStatus);
        scan.disabled = false;
      }
    },
    'primary',
  );
  const allOrphans = button('Select all eligible orphans', async () => {
    try {
      const data = await post('/storage/scan/show', {
        scan_id: view.scanId,
        orphans: true,
      });
      view.selected = data.selected_ids;
      await refresh();
    } catch (error) {
      clear(errors, errorBox(error));
    }
  });
  const review = button(
    'Review selected deletion',
    async () => {
      review.disabled = true;
      try {
        const plan = await post('/deletions/plan', {
          scan_id: view.scanId,
          selected: view.selected,
        });
        reviewPlan(plan, async (result) => {
          clear(
            errors,
            notice(
              `Deletion ${result.state}. Rescan to inspect current storage.`,
            ),
          );
          view.selected = [];
          view.scanId = null;
          await refresh();
        });
      } catch (error) {
        clear(errors, errorBox(error));
      } finally {
        review.disabled = !view.selected.length;
      }
    },
    'danger',
  );
  const planId = el('input', {
    placeholder: 'Deletion plan ID to inspect or resume',
  });
  const inspect = button('Inspect deletion job', async () => {
    try {
      reviewPlan(await post('/deletions/show', { plan_id: planId.value }), () =>
        scan.click(),
      );
    } catch (error) {
      clear(jobErrors, errorBox(error));
    }
  });
  const retention = el('div');
  const previewRetention = button('Preview retention', async () => {
    modal(
      'Deployment retention',
      el('div', { class: 'dialog-body' }, retention),
    );
    try {
      const result = await post('/retention', { apply: false });
      clear(
        retention,
        json(result),
        result.plan_id
          ? button(
              'Review retention deletion',
              async () => {
                try {
                  reviewPlan(
                    await post('/deletions/show', { plan_id: result.plan_id }),
                    () => scan.click(),
                  );
                } catch (error) {
                  clear(retention, errorBox(error));
                }
              },
              'danger',
            )
          : null,
      );
    } catch (error) {
      clear(retention, errorBox(error));
    }
  });
  const scanStatus = el('div');
  const screen = listScreen(
    [
      pageHeader(
        'Storage cleanup',
        'Inspect the configured Dockflow-owned directory or S3 bucket/prefix.',
        [
          scan,
          button('Deletion jobs', () =>
            modal(
              'Deletion jobs',
              el('div', {}, labeled('Plan ID', planId), inspect, jobErrors),
            ),
          ),
          previewRetention,
        ],
      ),
      el(
        'details',
        { open: window.matchMedia('(min-width: 761px)').matches },
        el('summary', {}, 'Scan options and filters'),
        notice(
          'Manually added artifacts require explicit deletion. Directory artifacts are selected as a whole; pins, references and publication records protect storage.',
        ),
        el(
          'div',
          { class: 'toolbar' },
          labeled('Subdirectory / prefix', prefix),
        ),
        el(
          'div',
          { class: 'toolbar' },
          labeled('Classification', classification),
          button('?', showClassificationHelp, 'classification-help-button', {
            'aria-label': 'Explain storage classifications',
            'aria-haspopup': 'dialog',
            title: 'Explain storage classifications',
          }),
          artifactFilter,
          button('Apply filters', async () => {
            view.classification = classification.value;
            view.artifactId = filterValue(artifactId).trim();
            view.page = null;
            view.history = [];
            await refresh(true);
          }),
        ),
      ),
      el(
        'div',
        { class: 'actions' },
        allOrphans,
        button('Clear selection', async () => {
          view.selected = [];
          await refresh();
        }),
        review,
      ),
      errors,
      scanStatus,
      location,
    ],
    results,
    el('div', {}, counters, pagination),
    'Storage files',
  );
  clear(container, screen);

  function totals(data) {
    const value = data?.totals || {
      selected_bytes: 0,
      orphan_bytes: 0,
      artifact_bytes: 0,
      protected_artifact_bytes: 0,
    };
    clear(
      counters,
      el(
        'div',
        { class: 'cleanup-metrics' },
        [
          ['Selected · estimated removable bytes', bytes(value.selected_bytes)],
          ['All eligible orphans', bytes(value.orphan_bytes)],
          ['All artifact payloads', bytes(value.artifact_bytes)],
          [
            'Protected artifact payloads',
            bytes(value.protected_artifact_bytes),
          ],
        ].map(([label, value]) =>
          el('div', {}, el('small', {}, label), el('strong', {}, value)),
        ),
      ),
      el(
        'small',
        { class: 'subtle' },
        data
          ? `Logical byte estimates across the entire scan. ${value.unknown_size_count ? value.unknown_size_count + ' unmeasured entries are excluded. ' : ''}Actual reclaimed disk space or billed capacity may differ.`
          : 'No completed scan. The displayed totals have not been measured.',
      ),
    );
  }
  async function refresh(resetScroll = false) {
    allOrphans.disabled = !view.scanId;
    review.disabled = !view.selected.length;
    if (!view.scanId) {
      totals(null);
      clear(
        results,
        table(fileHeaders, [], 'Start a scan to inspect managed storage.'),
      );
      clear(location);
      clear(
        pagination,
        el('span', {}, 'No completed scan'),
        el(
          'div',
          { class: 'actions' },
          button('Previous', () => {}, 'secondary', { disabled: true }),
          button('Next', () => {}, 'secondary', { disabled: true }),
        ),
      );
      return;
    }
    try {
      const data = await post('/storage/scan/show', {
        scan_id: view.scanId,
        selected: view.selected,
        page_token: view.page,
        classification: view.classification || null,
        artifact_id: view.artifactId || null,
      });
      const viewport = screen.querySelector('.list-content');
      const position = {
        top: resetScroll ? 0 : viewport.scrollTop,
        left: resetScroll ? 0 : viewport.scrollLeft,
      };
      view.selected = data.selected_ids;
      totals(data);
      const selected = new Set(view.selected);
      clear(
        retention,
        fields([
          [
            'Retention days',
            data.retention.days < 0 ? 'Disabled' : data.retention.days,
          ],
          ['Check interval', `${data.retention.interval_seconds} seconds`],
          ['Next check', data.retention.next_check_at || 'Not scheduled yet'],
        ]),
        data.retention.error ? notice(data.retention.error, 'error') : null,
      );
      clear(
        location,
        el('p', { class: 'cleanup-location' }, 'Location: ' + data.location),
        notice(
          `Scan ${data.scan_id} · ${data.state} · ${data.created_at} · ${data.totals.file_count} files/objects across the complete scan`,
        ),
      );
      clear(
        results,
        table(
          fileHeaders,
          data.items.map((row) => {
            const checkbox = el('input', {
              type: 'checkbox',
              checked: selected.has(row.id),
              disabled: !row.eligible,
              'aria-label': 'Select ' + row.path,
            });
            checkbox.addEventListener('change', async () => {
              const next = new Set(view.selected);
              if (checkbox.checked) next.add(row.id);
              else {
                // Clearing one member also clears its directory-artifact selection.
                for (const id of view.selected) next.delete(id);
                for (const id of removeSelection(
                  view.selected,
                  row.id,
                  data.selection_groups,
                ))
                  next.add(id);
              }
              view.selected = [...next];
              await refresh();
            });
            return [
              checkbox,
              el(
                'div',
                {},
                el('code', {}, row.path),
                row.identity?.version_id
                  ? el('small', {}, 'Version: ' + row.identity.version_id)
                  : null,
              ),
              bytes(row.size_bytes),
              row.classification.replaceAll('_', ' '),
              el(
                'div',
                {},
                row.artifact_ids.map((id) => link(id, 'artifacts/' + id)),
              ),
              row.blockers.join('; ') || 'Eligible',
            ];
          }),
        ),
      );
      clear(
        pagination,
        el(
          'span',
          {},
          `${data.items.length} files on this page · ${data.totals.file_count} across the scan${data.next_page_token ? ' · more available' : ''}`,
        ),
        el(
          'div',
          { class: 'actions' },
          button(
            'Previous',
            async () => {
              view.page = view.history.pop() || null;
              await refresh(true);
            },
            'secondary',
            { disabled: !view.history.length },
          ),
          button(
            'Next',
            async () => {
              view.history.push(view.page);
              view.page = data.next_page_token;
              await refresh(true);
            },
            'secondary',
            { disabled: !data.next_page_token },
          ),
        ),
      );
      viewport.scrollTop = position.top;
      viewport.scrollLeft = position.left;
      review.disabled = !view.selected.length;
    } catch (error) {
      clear(errors, errorBox(error));
    }
  }
  const fileHeaders = [
    'Select',
    'File / object',
    'Size',
    'Classification',
    'Artifacts',
    'Protection',
  ];
  await refresh();
}
