import assert from 'node:assert/strict';
import test from 'node:test';
import { plainLogEntries } from '../../src/dockflow_pipelines/static/logs.js';

test('terminal colors split across entries become plain text without HTML interpretation', () => {
  const entries = [
    { stream: 'stdout', text: '\x1b[3' },
    { stream: 'stderr', text: 'warning\n' },
    { stream: 'stdout', text: '2mTraining <script>...\x1b[0m\n' },
  ];
  const rendered = plainLogEntries(entries);
  assert.equal(rendered[0].text, '');
  assert.equal(rendered[1].text, 'warning\n');
  assert.equal(rendered[2].text, 'Training <script>...\n');
  assert.equal(entries[0].text, '\x1b[3');
});
