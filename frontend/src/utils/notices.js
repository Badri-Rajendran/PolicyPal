// The notices the server puts before an answer's text (ADR 0024, 0026). They
// are written by src/services/tools.py, not the model, and saved as the
// answer's leading paragraphs, so a loaded answer finds them by their wording.
// A match only changes how a paragraph looks; nothing is trusted because of it.
const NOTICES = [
  /^These are \d{4} plans and prices; \d{4} plans aren't available here yet, so check /,
  /^Summaries of Benefits and Coverage quoted here for .+ plans are for each plan's standard version; /,
];

export function splitNotices(content) {
  const paragraphs = content.split("\n\n");
  const notices = [];
  while (paragraphs.length > 0 && NOTICES.some((pattern) => pattern.test(paragraphs[0]))) {
    notices.push(paragraphs.shift());
  }
  return { notices, body: paragraphs.join("\n\n") };
}
