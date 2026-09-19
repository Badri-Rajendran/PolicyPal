// Document links come from CMS, not from us. Only a web address may become an
// href — never javascript:, data: or anything else a browser would run.
export function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
