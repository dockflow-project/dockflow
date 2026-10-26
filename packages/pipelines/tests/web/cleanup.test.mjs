import assert from 'node:assert/strict';
import test from 'node:test';
import { removeSelection } from '../../src/dockflow_pipelines/static/cleanup.js';

test('unselecting a directory member clears overlapping aliases across pages', () => {
  const groups = {
    first: ['page-one', 'shared'],
    second: ['shared', 'page-three'],
    unrelated: ['keep'],
  };
  assert.deepEqual(
    removeSelection(
      ['page-one', 'shared', 'page-three', 'keep'],
      'page-one',
      groups,
    ),
    ['keep'],
  );
});

test('unselecting an orphan preserves other individual selections', () => {
  assert.deepEqual(
    removeSelection(['orphan-one', 'orphan-two'], 'orphan-one'),
    ['orphan-two'],
  );
});
