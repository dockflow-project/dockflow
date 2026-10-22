import assert from 'node:assert/strict';
import test from 'node:test';
import { parseJson } from '../../src/dockflow_pipelines/static/json.js';

test('rejects duplicate keys, including escaped equivalent names and nested objects', () => {
  for (const source of [
    '{"a":1,"a":2}',
    '{"a":1,"\\u0061":2}',
    '[{"outer":{"a":1,"a":2}}]',
    '{"":1,"":2}',
  ]) {
    assert.throws(() => parseJson(source), /Duplicate JSON object key/);
  }
});

test('allows the same key in separate objects and punctuation in strings', () => {
  const value = [{ a: '{}[],:"\\' }, { a: 'value' }, { nested: { a: null } }];
  assert.deepEqual(parseJson(JSON.stringify(value)), value);
  assert.deepEqual(
    parseJson('  { "items" : [ {}, [], null, true, false, 1.25e2 ] }  '),
    { items: [{}, [], null, true, false, 125] },
  );
});

test('retains prototype-looking properties as ordinary own JSON data', () => {
  const value = parseJson(
    '{"__proto__":{"polluted":true},"constructor":"value"}',
  );
  assert.equal(Object.hasOwn(value, '__proto__'), true);
  assert.deepEqual(value.__proto__, { polluted: true });
  assert.equal({}.polluted, undefined);
  assert.equal(value.constructor, 'value');
});

test('native JSON syntax rules and top-level primitive values remain intact', () => {
  for (const source of [
    '{"a":}',
    '{"a":1,}',
    '[1,,2]',
    'undefined',
    '{a:1}',
    '"unterminated',
    '',
  ])
    assert.throws(() => parseJson(source));
  for (const source of ['null', 'true', 'false', '42', '"hello"', '[]', '{}'])
    assert.deepEqual(parseJson(source), JSON.parse(source));
  assert.throws(() => parseJson(null), /must be text/);
});
