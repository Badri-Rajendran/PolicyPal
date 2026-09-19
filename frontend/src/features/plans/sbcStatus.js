const NOT_READ = "Summary of Benefits not read here";

// Why a plan's Summary of Benefits could or couldn't be read (ADR 0017).
const NOTES = {
  ok: "Summary of Benefits read",
  no_link: "No Summary of Benefits listed",
  not_read: "Summary of Benefits not loaded yet",
  blocked: `${NOT_READ}: the insurer blocks automated access`,
  http_error: `${NOT_READ}: the insurer's link failed`,
  not_pdf: `${NOT_READ}: the link returned a web page`,
  too_large: `${NOT_READ}: the file is too large`,
  wrong_year: `${NOT_READ}: it is for another plan year`,
  unparseable: `${NOT_READ}: its text couldn't be read`,
};

// Null for a card saved before statuses were recorded, or one this app doesn't know.
export function sbcNote(status) {
  return Object.hasOwn(NOTES, status) ? NOTES[status] : null;
}

export function isUnreadable(status) {
  return Object.hasOwn(NOTES, status) && status !== "ok";
}
