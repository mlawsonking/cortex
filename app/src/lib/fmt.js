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
