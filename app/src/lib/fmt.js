// fmt.js - display formatting only. No business rules live here: taste rules, the 1987 year-floor, the H&R
// removal test and the compact-quality standard are all producer-side (guardrail 8). This file must never be the
// place a policy quietly gets re-implemented.

/** Bytes -> "12.3 TB" / "840 GB". Returns an em-dash-free placeholder for unknowns rather than "0 GB". */
export function bytes(n) {
  if (n === null || n === undefined || !Number.isFinite(n)) return '-';
  const gb = n / 1073741824;
  if (gb >= 1024) return (gb / 1024).toFixed(1) + ' TB';
  if (gb >= 1) return Math.round(gb) + ' GB';
  return Math.max(0, Math.round(n / 1048576)) + ' MB';
}

/** A count that might legitimately be unknown. Never coerce null to 0. */
export function count(n) {
  return (n === null || n === undefined || !Number.isFinite(n)) ? '-' : String(n);
}

export function pct(used, total) {
  if (!Number.isFinite(used) || !Number.isFinite(total) || total <= 0) return null;
  return Math.max(0, Math.min(100, (100 * used) / total));
}

export function fillClass(percent) {
  if (percent === null) return '';
  if (percent > 90) return 'crit';
  if (percent > 75) return 'warn';
  return '';
}

/** Bytes/sec -> "12.4 MB/s". */
export function speed(bps) {
  if (!Number.isFinite(bps)) return '-';
  return (bps / 1e6).toFixed(1) + ' MB/s';
}

/** Unix seconds -> "4m" / "3h" / "2d". ts===0 means the source gave no parseable date: say so, never guess. */
export function since(ts, nowMs) {
  if (!Number.isFinite(ts) || ts <= 0) return 'undated';
  const s = Math.max(0, nowMs / 1000 - ts);
  if (s < 90) return 'now';
  if (s < 5400) return Math.round(s / 60) + 'm';
  if (s < 172800) return Math.round(s / 3600) + 'h';
  return Math.round(s / 86400) + 'd';
}

/** "2026-08-04" -> "today" / "tomorrow" / "Tue 04 Aug". Local-time comparison, no UTC drift. */
export function dayLabel(dateStr, nowMs) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr || '');
  if (!m) return dateStr || '?';
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const today = new Date(nowMs);
  const days = Math.round((d - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'tomorrow';
  // Always show the year when it is not the current one. A bare "Tue, Oct 25" inside a card headed
  // "next 14 days" read as upcoming when the underlying date was 2022.
  const opts = { weekday: 'short', day: '2-digit', month: 'short' };
  if (d.getFullYear() !== today.getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString(undefined, opts);
}
