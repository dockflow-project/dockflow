/** Mutation forms use the same public APIs as the CLI/KFP clients. */
import {
  el,
  button,
  clear,
  labeled,
  modal,
  errorBox,
  notice,
  json,
  toast,
  link,
  section,
  pageHeader,
} from './dom.js';
import { get, post, request, collect } from './api.js';
import { parseJson } from './json.js';

function dialogForm(title, content, action, label = 'Create') {
  const errors = el('div');
  const submit = el('button', { type: 'submit', class: 'primary' }, label);
  const form = el(
    'form',
    {},
    content,
    errors,
    el('div', { class: 'actions' }, submit),
  );
  const dialog = modal(title, form);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Working…';
    form.setAttribute('aria-busy', 'true');
    clear(errors);
    try {
      await action();
      dialog.close();
    } catch (error) {
      if (error.name !== 'AbortError') clear(errors, errorBox(error));
    } finally {
      submit.disabled = false;
      submit.textContent = label;
      form.removeAttribute('aria-busy');
    }
  });
  return dialog;
}
export function uploadPipeline(pipeline, done) {
  const name = el('input', {
    type: 'text',
    maxlength: 256,
    required: Boolean(pipeline),
    placeholder: pipeline ? 'Version name' : 'Use compiled pipeline name',
  });
  const description = el('textarea', {
    maxlength: 4096,
    placeholder: 'Optional description',
  });
  const file = el('input', {
    type: 'file',
    accept: '.yaml,.yml,.json',
    required: true,
  });
  dialogForm(
    pipeline ? 'Upload version' : 'Upload pipeline',
    el(
      'div',
      {},
      notice(
        'Upload a compiled KFP YAML or JSON definition. Component images must already be available to the execution Docker engine.',
      ),
      labeled(pipeline ? 'Version name' : 'Pipeline name', name),
      labeled('Compiled definition', file),
      labeled('Description', description),
    ),
    async () => {
      const form = new FormData();
      form.append('uploadfile', file.files[0]);
      const query = new URLSearchParams({ description: description.value });
      if (name.value) query.set('name', name.value);
      if (pipeline) query.set('pipelineid', pipeline.pipeline_id);
      const result = await request(
        '/apis/v2beta1/pipelines/' +
          (pipeline ? 'upload_version' : 'upload') +
          '?' +
          query,
        { method: 'POST', body: form },
      );
      toast('Definition registered');
      done(result);
    },
    'Upload',
  );
}
export function createExperiment(done) {
  const name = el('input', { required: true, maxlength: 256 });
  const description = el('textarea', { maxlength: 4096 });
  dialogForm(
    'Create experiment',
    el('div', {}, labeled('Name', name), labeled('Description', description)),
    async () => {
      const result = await post('/experiments', {
        display_name: name.value,
        description: description.value,
      });
      toast('Experiment created');
      done(result);
    },
  );
}
export function createArtifact(done) {
  const operation = el(
    'select',
    {},
    el('option', { value: 'import' }, 'Import · managed copy'),
    el('option', { value: 'register' }, 'Register · external reference'),
  );
  const uri = el('input', {
    required: true,
    placeholder: 'file:///data/dataset.csv or s3://bucket/key',
  });
  const type = el('input', { required: true, value: 'system.Dataset' }),
    version = el('input', { required: true, value: '0.0.1' }),
    revision = el('input', { placeholder: 'Optional data revision' }),
    metadata = el('textarea', {}, '{}');
  dialogForm(
    'Register or import artifact',
    el(
      'div',
      {},
      notice(
        'The URI must be visible to the service and within its configured allowlist. Import copies the bytes to managed storage; register keeps an external reference. This form does not upload a file from your browser.',
      ),
      labeled('Operation', operation),
      labeled('Source URI', uri),
      el(
        'div',
        { class: 'form-grid' },
        labeled('Type schema', type),
        labeled('Type schema version', version),
      ),
      labeled('Data revision', revision),
      labeled('Metadata (JSON object)', metadata),
    ),
    async () => {
      const body = {
        operation: operation.value,
        uri: uri.value,
        type: { schema_title: type.value, schema_version: version.value },
        metadata: parseObject(metadata.value, 'Metadata'),
      };
      if (revision.value) body.version = revision.value;
      const result = await post('/artifacts', body);
      toast('Artifact accepted');
      done(result);
    },
  );
}
export function uploadArtifact(done) {
  const file = el('input', { type: 'file', required: true });
  const mode = el(
    'select',
    {},
    el('option', { value: 'keep' }, 'Keep ZIP file as an artifact'),
    el('option', { value: 'extract' }, 'Extract into a directory artifact'),
  );
  const archive = el('div', { hidden: true }, labeled('ZIP handling', mode));
  file.addEventListener('change', () => {
    archive.hidden = !file.files[0]?.name.toLowerCase().endsWith('.zip');
    if (archive.hidden) mode.value = 'keep';
  });
  const type = el('input', { required: true, value: 'system.Artifact' }),
    version = el('input', { required: true, value: '0.0.1' }),
    revision = el('input', { placeholder: 'Optional data revision' }),
    metadata = el('textarea', {}, '{}');
  dialogForm(
    'Upload artifact',
    el(
      'div',
      {},
      notice(
        'Upload and register a manually added artifact in managed storage. No run is needed. Manually added artifacts are deleted only explicitly.',
      ),
      labeled('File', file),
      archive,
      el(
        'div',
        { class: 'form-grid' },
        labeled('Type schema', type),
        labeled('Type schema version', version),
      ),
      labeled('Data revision', revision),
      labeled('Metadata (JSON object)', metadata),
      notice(
        'The deployment upload limit applies (16 MiB by default, including request overhead). ZIP extraction allows up to 256 MiB and 10,000 entries. Existing artifacts are never overwritten.',
      ),
    ),
    async () => {
      const options = {
        type: { schema_title: type.value, schema_version: version.value },
        metadata: parseObject(metadata.value, 'Metadata'),
        archive_mode: mode.value,
      };
      if (revision.value) options.version = revision.value;
      const body = new FormData();
      body.append('options', JSON.stringify(options));
      body.append('uploadfile', file.files[0]);
      const result = await request('/dockflow/v1/artifacts/upload', {
        method: 'POST',
        body,
      });
      toast('Artifact uploaded and registered');
      done(result);
    },
    'Upload and register',
  );
}
export function confirmAction(title, message, action, done) {
  dialogForm(
    title,
    el('p', {}, message),
    async () => {
      await action();
      done?.();
    },
    'Confirm',
  );
}
export function parseParameter(value, type) {
  if (type === 'STRING') return value;
  if (type === 'BOOLEAN') {
    if (value !== 'true' && value !== 'false')
      throw new Error('Expected true or false.');
    return value === 'true';
  }
  if (type === 'NUMBER_INTEGER' || type === 'NUMBER_DOUBLE') {
    if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value.trim()))
      throw new Error('Expected a JSON number.');
    const number = Number(value);
    if (
      !Number.isFinite(number) ||
      (Number.isInteger(number) && !Number.isSafeInteger(number)) ||
      (type === 'NUMBER_INTEGER' && !Number.isInteger(number))
    )
      throw new Error(
        'Use a finite number (and a safe integer for integer parameters).',
      );
    return number;
  }
  if (!['LIST', 'STRUCT'].includes(type))
    throw new Error('Unsupported parameter type: ' + type);
  const parsed = parseJson(value);
  validatePortable(parsed);
  if (type === 'LIST' && !Array.isArray(parsed))
    throw new Error('Expected a JSON array.');
  if (
    type === 'STRUCT' &&
    (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
  )
    throw new Error('Expected a JSON object.');
  return parsed;
}
function validatePortable(value) {
  if (
    typeof value === 'number' &&
    (!Number.isFinite(value) ||
      (Number.isInteger(value) && !Number.isSafeInteger(value)))
  )
    throw new Error('JSON numbers must be finite and integers must be safe.');
  if (value && typeof value === 'object')
    for (const child of Object.values(value)) validatePortable(child);
}
function parseObject(value, name) {
  const result = parseJson(value);
  validatePortable(result);
  if (!result || typeof result !== 'object' || Array.isArray(result))
    throw new Error(name + ' must be a JSON object.');
  return result;
}
function parameterField(name, contract, provided) {
  const type = contract.parameterType || 'STRING',
    optional = contract.isOptional || Object.hasOwn(contract, 'defaultValue');
  const initial = provided !== undefined ? provided : contract.defaultValue;
  const control =
    type === 'BOOLEAN'
      ? el(
          'select',
          {},
          el('option', { value: 'true' }, 'true'),
          el('option', { value: 'false' }, 'false'),
        )
      : type === 'STRUCT' || type === 'LIST'
        ? el('textarea')
        : el('input', {
            type: 'text',
            inputmode: type.startsWith('NUMBER') ? 'decimal' : 'text',
          });
  control.value =
    initial === undefined
      ? ''
      : typeof initial === 'object'
        ? JSON.stringify(initial, null, 2)
        : String(initial);
  if (type === 'BOOLEAN' && initial === undefined) control.value = 'false';
  const include = el('input', {
    type: 'checkbox',
    checked: !optional || initial !== undefined,
  });
  if (optional) {
    control.disabled = !include.checked;
    include.addEventListener(
      'change',
      () => (control.disabled = !include.checked),
    );
  }
  const wrapper = el(
    'div',
    {},
    labeled(
      `${name} · ${type}${optional ? '' : ' · required'}`,
      control,
      contract.description ||
        (Object.hasOwn(contract, 'defaultValue')
          ? 'Default: ' + JSON.stringify(contract.defaultValue)
          : ''),
    ),
    optional
      ? el('label', { class: 'inline-check' }, include, 'Include ' + name)
      : null,
  );
  return {
    wrapper,
    read: () =>
      !optional || include.checked
        ? parseParameter(control.value, type)
        : undefined,
  };
}
export async function runForm(container, query, navigate) {
  const source = query.get('clone')
    ? await get('/runs/' + query.get('clone'))
    : null;
  const [definitions, experiments, artifacts] = await Promise.all([
    collect('/definitions'),
    collect('/experiments'),
    collect('/artifacts'),
  ]);
  const definitionInput = el('input', {
    required: true,
    placeholder: 'Choose a version or paste its Pipeline ID',
    list: 'definition-options',
  });
  const initial = query.get('definition') || source?.definition_id || '';
  definitionInput.value = initial;
  const options = el(
    'datalist',
    { id: 'definition-options' },
    definitions.items.map((d) =>
      el(
        'option',
        { value: d.definition_id },
        `${d.name || 'Inline'} · ${d.version_name || d.definition_id.slice(-8)}`,
      ),
    ),
  );
  const name = el('input', {
    maxlength: 256,
    placeholder: 'Use pipeline name',
    value: source ? source.display_name + ' (copy)' : '',
  });
  const description = el(
    'textarea',
    { maxlength: 4096 },
    source?.description || '',
  );
  const experiment = el(
    'select',
    {},
    el('option', { value: '' }, 'Default'),
    experiments.items.map((e) =>
      el('option', { value: e.experiment_id }, e.display_name),
    ),
  );
  experiment.value = query.get('experiment') || source?.experiment_id || '';
  const scope = el(
    'select',
    {},
    ['global', 'keyed', 'run', 'none'].map((v) =>
      el(
        'option',
        { value: v },
        v === 'none' ? 'none · execute every step' : v,
      ),
    ),
  );
  scope.value = source?.reuse?.scope || 'global';
  const key = el('input', {
    value: source?.reuse?.key || '',
    placeholder: 'Required for keyed reuse',
  });
  key.disabled = scope.value !== 'keyed';
  scope.addEventListener(
    'change',
    () => (key.disabled = scope.value !== 'keyed'),
  );
  const selection = el(
    'textarea',
    {},
    JSON.stringify(source?.selection || { mode: 'full' }, null, 2),
  );
  const bindings = el(
    'textarea',
    {},
    JSON.stringify(source?.bindings || {}, null, 2),
  );
  const executions = el(
    'textarea',
    {},
    JSON.stringify(source?.use_executions || {}, null, 2),
  );
  const contracts = el('div');
  const errors = el('div');
  const validation = el('div');
  let current = null,
    parameterControls = [],
    artifactControls = [],
    contractRequest = 0;
  async function loadContracts() {
    const generation = ++contractRequest;
    current = null;
    clear(contracts, notice('Loading version inputs…'));
    clear(errors);
    parameterControls = [];
    artifactControls = [];
    if (!definitionInput.value) {
      clear(contracts, notice('Choose a definition to configure its inputs.'));
      return;
    }
    try {
      const definition = await get(
        '/definitions/' + encodeURIComponent(definitionInput.value),
      );
      if (generation !== contractRequest) return;
      current = definition;
      const root =
        definition.pipeline_spec.root ||
        definition.pipeline_spec.pipelineSpec?.root;
      parameterControls = Object.entries(
        root?.inputDefinitions?.parameters || {},
      ).map(([n, c]) => ({
        name: n,
        ...parameterField(n, c, source?.parameters?.[n]),
      }));
      const artifactOptions = el(
        'datalist',
        { id: 'artifact-options' },
        artifacts.items.map((a) =>
          el(
            'option',
            { value: a.artifact_id },
            `${a.type.schema_title} · ${a.version || a.content_uri || a.artifact_id}`,
          ),
        ),
      );
      artifactControls = Object.entries(
        root?.inputDefinitions?.artifacts || {},
      ).map(([n, c]) => {
        const input = el('input', {
          list: 'artifact-options',
          required: !c.isOptional,
          value: source?.inputs?.[n] || '',
          placeholder: 'artifact_…',
        });
        return {
          name: n,
          input,
          wrapper: labeled(
            `${n} · ${c.artifactType?.schemaTitle || 'Artifact'}${c.isOptional ? '' : ' · required'}`,
            input,
            c.description,
          ),
        };
      });
      clear(
        contracts,
        section(
          'Inputs',
          link(
            'Inspect ' + (definition.name || definition.definition_id),
            'definitions/' + definition.definition_id,
          ),
          el(
            'div',
            { class: 'form-grid' },
            parameterControls.map((p) => p.wrapper),
            artifactControls.map((p) => p.wrapper),
          ),
          artifactOptions,
          ...(!parameterControls.length && !artifactControls.length
            ? [
                el(
                  'p',
                  { class: 'subtle' },
                  'This definition has no root inputs.',
                ),
              ]
            : []),
        ),
      );
    } catch (error) {
      if (generation === contractRequest && error.name !== 'AbortError')
        clear(contracts, errorBox(error));
    }
  }
  definitionInput.addEventListener('change', loadContracts);
  const submit = el(
    'button',
    { type: 'submit', class: 'primary' },
    'Start run',
  );
  let savedPayload = '',
    idempotencyKey = '';
  function payload() {
    if (!current || current.definition_id !== definitionInput.value)
      throw new Error(
        'Choose a valid definition and wait for its input contract.',
      );
    const parameters = Object.create(null),
      inputs = Object.create(null);
    for (const control of parameterControls) {
      const value = control.read();
      if (value !== undefined) parameters[control.name] = value;
    }
    for (const { name, input } of artifactControls)
      if (input.value) inputs[name] = input.value;
    const body = {
      definition_id: current.definition_id,
      parameters,
      inputs,
      description: description.value,
      reuse: { scope: scope.value },
      selection: parseObject(selection.value, 'Selection'),
      bindings: parseObject(bindings.value, 'Bindings'),
      use_executions: parseObject(executions.value, 'Historical executions'),
    };
    if (name.value) body.display_name = name.value;
    if (experiment.value) body.experiment_id = experiment.value;
    if (scope.value === 'keyed') body.reuse.key = key.value;
    return body;
  }
  const validate = button('Validate inputs', async () => {
    validate.disabled = true;
    clear(errors);
    try {
      const body = payload();
      const result = await post('/definitions/validate', {
        definition_id: body.definition_id,
        parameters: body.parameters,
        inputs: body.inputs,
      });
      clear(
        validation,
        notice(
          'Definition and root inputs are valid. The complete execution plan is checked on submission.',
          'success',
        ),
        result.diagnostics?.length ? json(result.diagnostics) : null,
      );
    } catch (error) {
      clear(validation);
      clear(errors, errorBox(error));
    } finally {
      validate.disabled = false;
    }
  });
  const form = el(
    'form',
    {},
    section(
      'Run configuration',
      el(
        'div',
        { class: 'form-grid' },
        el('div', {}, labeled('Definition version', definitionInput), options),
        labeled('Experiment', experiment),
        labeled('Run name', name),
        labeled('Description', description),
      ),
    ),
    contracts,
    section(
      'Execution policy',
      el(
        'div',
        { class: 'form-grid' },
        labeled(
          'Reuse scope',
          scope,
          'Compiled component caching settings still apply.',
        ),
        labeled('Reuse key', key),
      ),
      el(
        'details',
        {},
        el('summary', {}, 'Advanced selection and historical bindings'),
        labeled('Selection (JSON)', selection),
        labeled('Artifact bindings (JSON)', bindings),
        labeled('Historical executions (JSON)', executions),
      ),
    ),
    validation,
    errors,
    el(
      'div',
      { class: 'actions' },
      submit,
      validate,
      button('Cancel', () => history.back()),
    ),
  );
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    validate.disabled = true;
    clear(errors);
    try {
      const body = payload();
      const serialized = JSON.stringify(body);
      if (serialized !== savedPayload) {
        idempotencyKey = crypto.randomUUID();
        savedPayload = serialized;
      }
      const run = await post('/runs', body, {
        'Idempotency-Key': idempotencyKey,
      });
      toast('Run accepted');
      navigate('runs/' + run.run_id);
    } catch (error) {
      if (error.name !== 'AbortError') clear(errors, errorBox(error));
    } finally {
      submit.disabled = false;
      validate.disabled = false;
    }
  });
  clear(
    container,
    pageHeader(
      source ? 'Clone run' : 'Create run',
      'Select an immutable definition version and configure this execution.',
    ),
    definitions.truncated || experiments.truncated || artifacts.truncated
      ? notice(
          'Selectors show the first 2,000 records. You can paste any known definition or artifact ID.',
        )
      : null,
    form,
  );
  await loadContracts();
}
