/** Plain text display of terminal colors, including escapes split across records. */
export function plainLogEntries(entries) {
  const pending = new Map();
  return entries.map((entry) => {
    const key = `${entry.attempt_id || ''}:${entry.stream}`;
    let text = (pending.get(key) || '') + entry.text;
    const tail = text.match(/\x1b(?:\[[0-9;:]*)?$/);
    pending.set(key, tail ? tail[0] : '');
    if (tail) text = text.slice(0, -tail[0].length);
    return { ...entry, text: text.replace(/\x1b\[[0-9;:]*m/g, '') };
  });
}
