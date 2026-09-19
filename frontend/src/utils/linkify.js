import { safeUrl } from "./safeUrl";

const HTTPS_URL = /https:\/\/[^\s<>"'`]+/g;
// Sentence punctuation after a link is not part of it.
const TRAILING = /[.,;:!?)\]*]+$/;

// Text split into plain runs and https links. Only what safeUrl accepts
// becomes a link; anything else stays text.
export function linkify(text) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(HTTPS_URL)) {
    const raw = match[0].replace(TRAILING, "");
    const href = safeUrl(raw);
    if (!href) continue;
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    parts.push({ text: raw, href });
    last = match.index + raw.length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
