/** JSON.parse validates syntax; this pass prevents silent duplicate-key loss. */
export function parseJson(source) {
  if (typeof source !== 'string')
    throw new TypeError('JSON input must be text.');
  const value = JSON.parse(source);
  // Tokenize only after native syntax validation. Strings remain intact, so
  // punctuation inside a string cannot affect object or array boundaries.
  const tokens =
    source.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]|[^\s{}\[\],:]+/gs) || [];
  let position = 0;
  function visit() {
    const token = tokens[position++];
    if (token === '{') {
      const keys = new Set();
      if (tokens[position] === '}') {
        position++;
        return;
      }
      while (true) {
        const key = JSON.parse(tokens[position++]);
        if (keys.has(key))
          throw new Error('Duplicate JSON object key: ' + JSON.stringify(key));
        keys.add(key);
        position++; // The colon was already checked by JSON.parse.
        visit();
        if (tokens[position++] === '}') return;
      }
    }
    if (token === '[') {
      if (tokens[position] === ']') {
        position++;
        return;
      }
      while (true) {
        visit();
        if (tokens[position++] === ']') return;
      }
    }
  }
  visit();
  if (position !== tokens.length)
    throw new Error('Invalid JSON token structure.');
  return value;
}
