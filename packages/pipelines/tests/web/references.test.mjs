import assert from 'node:assert/strict';
import test from 'node:test';
import {
  identity,
  referenceCaption,
} from '../../src/dockflow_pipelines/static/references.js';

const id = 'attempt_12345678-1111-4111-8111-111111111111';
test('reference identity accepts public IDs and rejects partial/mismatched values', () => {
  assert.deepEqual(identity(id), { collection: 'attempts', id });
  for (const value of [
    '',
    '12345678',
    '../file',
    'attempt_new',
    'artifact_12345678-1111-4111-8111-111111111111',
  ])
    assert.equal(identity(value), null);
});
test('context preserves invocation labels and exact visible IDs', () => {
  assert.equal(
    referenceCaption('Attempt 1 · 12345678', 'comp-train', id),
    'comp-train · Attempt 1 · 12345678',
  );
  assert.equal(
    referenceCaption('Morning invocation', 'training-pipeline', id),
    'training-pipeline · Morning invocation · 12345678',
  );
  assert.equal(referenceCaption(id, 'comp-train', id), 'comp-train · ' + id);
});
test('existing names and adjacent table IDs are not duplicated', () => {
  assert.equal(
    referenceCaption('Experiment name', 'Experiment name', id, true),
    'Experiment name',
  );
  assert.equal(
    referenceCaption('Run invocation', 'pipeline-name', id, true),
    'pipeline-name · Run invocation',
  );
});
test('unavailable and markup-shaped names stay plain caption text', () => {
  assert.equal(
    referenceCaption('12345678', null, id),
    'Name unavailable · 12345678',
  );
  assert.equal(
    referenceCaption('Task', '<img src=x onerror=alert(1)>', id),
    '<img src=x onerror=alert(1)> · Task · 12345678',
  );
});
