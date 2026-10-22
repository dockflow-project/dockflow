import assert from 'node:assert/strict';
import test from 'node:test';
import { parseParameter } from '../../src/dockflow_pipelines/static/forms.js';

test('string parameters preserve empty strings, numeric-looking text and Unicode', () => {
  for (const value of ['', '001', 'false', '  data  ', '模型'])
    assert.equal(parseParameter(value, 'STRING'), value);
});

test('boolean parameters accept only explicit true or false values', () => {
  assert.equal(parseParameter('true', 'BOOLEAN'), true);
  assert.equal(parseParameter('false', 'BOOLEAN'), false);
  for (const value of ['', 'TRUE', '1', 'no', 'null'])
    assert.throws(() => parseParameter(value, 'BOOLEAN'));
});

test('integer parameters preserve portable boundaries and reject fractions or overflow', () => {
  for (const value of ['0', '-9', '9007199254740991', '-9007199254740991'])
    assert.equal(parseParameter(value, 'NUMBER_INTEGER'), Number(value));
  for (const value of [
    '',
    ' ',
    '1.2',
    '9007199254740992',
    '-9007199254740992',
    '1e400',
    'NaN',
    'Infinity',
  ])
    assert.throws(() => parseParameter(value, 'NUMBER_INTEGER'));
});

test('double parameters admit finite decimal/exponential values without boolean coercion', () => {
  assert.equal(parseParameter('1.25', 'NUMBER_DOUBLE'), 1.25);
  assert.equal(parseParameter('2.5e-3', 'NUMBER_DOUBLE'), 0.0025);
  for (const value of [
    '',
    'true',
    'NaN',
    'Infinity',
    '-Infinity',
    '1e400',
    '9007199254740993',
  ])
    assert.throws(() => parseParameter(value, 'NUMBER_DOUBLE'));
});

test('structured parameters retain valid nested JSON values and enforce their root type', () => {
  assert.deepEqual(parseParameter('[1,"two",false,null,{"x":0.25}]', 'LIST'), [
    1,
    'two',
    false,
    null,
    { x: 0.25 },
  ]);
  assert.deepEqual(parseParameter('{"items":[1,2],"enabled":true}', 'STRUCT'), {
    items: [1, 2],
    enabled: true,
  });
  for (const value of ['{}', 'null', '"text"', '1'])
    assert.throws(() => parseParameter(value, 'LIST'));
  for (const value of ['[]', 'null', '"text"', '1'])
    assert.throws(() => parseParameter(value, 'STRUCT'));
});

test('nested overflow and unsafe integers are rejected before JSON serialization can change them', () => {
  for (const [value, type] of [
    ['[1e400]', 'LIST'],
    ['{"nested":{"number":-1e400}}', 'STRUCT'],
    ['[9007199254740993]', 'LIST'],
    ['{"number":9007199254740992}', 'STRUCT'],
  ])
    assert.throws(() => parseParameter(value, type));
});

test('unsupported parameter types fail explicitly', () => {
  for (const type of ['UNKNOWN', 'NUMBER', ''])
    assert.throws(() => parseParameter('1', type));
});

test('structured parameter text does not silently discard duplicate fields', () => {
  assert.throws(
    () => parseParameter('{"rate":1,"rate":2}', 'STRUCT'),
    /Duplicate JSON object key/,
  );
  assert.throws(
    () => parseParameter('[{"rate":1,"rate":2}]', 'LIST'),
    /Duplicate JSON object key/,
  );
});
