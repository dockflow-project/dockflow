import assert from 'node:assert/strict';
import test from 'node:test';
import { graphModel } from '../../src/dockflow_pipelines/static/graph.js';

function fixture() {
  return {
    pipelineInfo: { name: 'nested-example' },
    root: {
      dag: {
        tasks: {
          source: { componentRef: { name: 'leaf' } },
          train: {
            componentRef: { name: 'group' },
            dependentTasks: ['source'],
            inputs: {
              parameters: {
                seed: {
                  taskOutputParameter: {
                    producerTask: 'source',
                    outputParameterKey: 'value',
                  },
                },
              },
            },
          },
          evaluate: {
            componentRef: { name: 'leaf' },
            inputs: {
              artifacts: {
                model: {
                  taskOutputArtifact: {
                    producerTask: 'train',
                    outputArtifactKey: 'model',
                  },
                },
              },
            },
          },
        },
      },
    },
    components: {
      leaf: { executorLabel: 'leaf-executor' },
      group: {
        dag: {
          tasks: {
            prepare: {
              componentRef: { name: 'leaf' },
              inputs: {
                parameters: { seed: { componentInputParameter: 'seed' } },
              },
            },
            fit: {
              componentRef: { name: 'leaf' },
              inputs: {
                parameters: {
                  data: {
                    taskOutputParameter: {
                      producerTask: 'prepare',
                      outputParameterKey: 'prepared',
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  };
}

test('derives explicit and parameter/artifact dependencies without duplicate edges', () => {
  const model = graphModel(fixture());
  assert.deepEqual(
    model.edges.filter((edge) => edge.kind === 'dependency'),
    [
      { from: 'source', to: 'train', kind: 'dependency' },
      { from: 'train/prepare', to: 'train/fit', kind: 'dependency' },
      { from: 'train', to: 'evaluate', kind: 'dependency' },
    ],
  );
});

test('keeps nested qualified task identities and separate containment edges', () => {
  const model = graphModel(fixture());
  assert.deepEqual(
    model.nodes.map((node) => [node.name, node.parent, node.group]),
    [
      ['source', null, false],
      ['train', null, true],
      ['train/prepare', 'train', false],
      ['train/fit', 'train', false],
      ['evaluate', null, false],
    ],
  );
  assert.deepEqual(
    model.edges.filter((edge) => edge.kind === 'containment'),
    [
      { from: 'train', to: 'train/prepare', kind: 'containment' },
      { from: 'train', to: 'train/fit', kind: 'containment' },
    ],
  );
});

test('projects each invocation of a reused nested component independently', () => {
  const spec = fixture();
  spec.root.dag.tasks.again = { componentRef: { name: 'group' } };
  const model = graphModel(spec);
  assert.ok(model.nodes.some((node) => node.name === 'train/fit'));
  assert.ok(model.nodes.some((node) => node.name === 'again/fit'));
  assert.ok(
    model.edges.some(
      (edge) => edge.from === 'again/prepare' && edge.to === 'again/fit',
    ),
  );
  assert.equal(
    model.edges.some(
      (edge) => edge.from === 'train/prepare' && edge.to === 'again/fit',
    ),
    false,
  );
});

test('handles wrapped PipelineSpec and primitive component roots', () => {
  assert.deepEqual(
    graphModel({ pipelineSpec: fixture() }),
    graphModel(fixture()),
  );
  const model = graphModel({
    pipelineInfo: { name: 'standalone' },
    root: { executorLabel: 'exec' },
  });
  assert.deepEqual(
    model.nodes.map((node) => [
      node.name,
      node.label,
      node.component.executorLabel,
    ]),
    [['root', 'standalone', 'exec']],
  );
  assert.deepEqual(model.edges, []);
});

test('retains untrusted names and condition text as data without evaluation', () => {
  const spec = fixture();
  const label = '<img src=x onerror="globalThis.compromised=true">';
  spec.root.dag.tasks.source.taskInfo = { name: label };
  spec.root.dag.tasks.source.triggerPolicy = {
    condition: 'globalThis.compromised = true',
  };
  const model = graphModel(spec);
  assert.equal(model.nodes[0].label, label);
  assert.equal(
    model.nodes[0].task.triggerPolicy.condition,
    'globalThis.compromised = true',
  );
  assert.equal(globalThis.compromised, undefined);
});

test('recursive or missing component references do not recurse indefinitely', () => {
  const spec = {
    root: {
      dag: {
        tasks: {
          outer: { componentRef: { name: 'recursive' } },
          missing: { componentRef: { name: 'absent' } },
        },
      },
    },
    components: {
      recursive: {
        dag: { tasks: { self: { componentRef: { name: 'recursive' } } } },
      },
    },
  };
  assert.deepEqual(
    graphModel(spec).nodes.map((node) => node.name),
    ['outer', 'outer/self', 'missing'],
  );
});
