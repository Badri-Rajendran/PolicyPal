const LABELS = ["Today", "Previous 7 days", "Earlier"];

// Threads by their last activity, in local days. Calendar arithmetic, not
// 7 × 24 hours, so a daylight-saving change can't move the boundary.
export function groupThreads(threads, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const weekAgo = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7).getTime();
  const groups = LABELS.map((label) => ({ label, threads: [] }));
  for (const thread of threads) {
    const at = new Date(thread.updated_at).getTime();
    const group = at >= today ? 0 : at >= weekAgo ? 1 : 2;
    groups[group].threads.push(thread);
  }
  return groups.filter((g) => g.threads.length > 0);
}
