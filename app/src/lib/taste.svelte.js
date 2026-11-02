// Taste loop client helpers (wg\GAMEPLAN-TASTE-LOOP-2026-11.md s6). One shared taste-ledger contract (the thumbs
// map every page renders from) + one shared rate-queue contract (home card, #/rate page, nav badge), plus thin
// wrappers over the three verbs. The server re-checks everything; these only shape requests and replies.
import { Contract } from './contracts.svelte.js';
import { act } from './act.js';

export const ledger = new Contract('taste-ledger', 120000);
export const queue = new Contract('rate-queue', 120000);

// Optimistic thumb overrides until the next taste-ledger read catches up: key -> 'up' | 'down' | null (cleared).
export const thumbs = $state({ local: {} });

export function thumbOf(key) {
  if (key in thumbs.local) return thumbs.local[key];
  return ledger.data?.thumbs?.[key] ?? null;
}

export async function thumb(key, signal) {
  const before = thumbs.local[key];
  thumbs.local[key] = signal === 'clear' ? null : signal;
  try {
    return JSON.parse(await act('taste-feedback', 'key=' + encodeURIComponent(key) + '&signal=' + signal));
  } catch (e) {
    if (before === undefined) delete thumbs.local[key];
    else thumbs.local[key] = before;
    throw e;
  }
}

/** value: 1-10 | 'skip' | 'notme' | 'bailed'. Resolves to the server reply {ok, event_id, guess, plex, ...}. */
export async function rate(key, value, surface = 'rate') {
  return JSON.parse(await act('rate-title', 'key=' + encodeURIComponent(key) + '&value=' + encodeURIComponent(value)
    + '&surface=' + surface));
}

export async function undo(key, eventId) {
  return JSON.parse(await act('rate-title', 'key=' + encodeURIComponent(key) + '&value=undo:' + encodeURIComponent(eventId)));
}

export async function queueWatch(ratingKey) {
  return JSON.parse(await act('queue-watch', 'op=add&rating_key=' + encodeURIComponent(ratingKey)));
}

export async function search(q) {
  const res = await fetch('/taste-search?q=' + encodeURIComponent(q), { cache: 'no-store' });
  if (!res.ok) throw new Error('search HTTP ' + res.status);
  return res.json();
}

export function stars(v) {
  const n = v / 2;
  return '★'.repeat(Math.floor(n)) + (n % 1 ? '½' : '');
}
