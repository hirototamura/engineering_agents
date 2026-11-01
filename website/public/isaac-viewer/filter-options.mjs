// Preserve the archived SI number through HTML option values and share links.
// Unit conversion and rounding affect only the text shown to the reader.
export function factorOptions(values, unit='', displayScale=1) {
  return [...new Set(values)].map(value => ({
    value: String(value),
    label: `${displayScale===1 ? value : Number((value*displayScale).toFixed(6))}${unit}`,
  }));
}
