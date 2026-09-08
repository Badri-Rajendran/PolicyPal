export function formatSourceLabel(filename) {
  return filename
    .replace(/^wiki_/, "")
    .replace(/\.[^.]+$/, "")
    .replaceAll("_", " ");
}

export function formatTime(isoString) {
  return new Date(isoString).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
