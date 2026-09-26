function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function matches(text, query) {
  return text.toLowerCase().includes(query.trim().toLowerCase());
}

// A title split into runs, marking each case-insensitive match of the query,
// for <mark>. Never HTML: the parts are rendered as text.
export function highlight(text, query) {
  const needle = query.trim();
  if (!needle) return [{ text, match: false }];
  return text
    .split(new RegExp(`(${escapeRegExp(needle)})`, "gi"))
    .filter(Boolean)
    .map((part) => ({ text: part, match: part.toLowerCase() === needle.toLowerCase() }));
}
