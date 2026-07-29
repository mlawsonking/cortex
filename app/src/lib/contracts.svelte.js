// contracts.svelte.js - the ONLY way this app gets data. Fetches a named contract, refuses anything that is not a
// proper envelope, and reports freshness from the contract's own _meta. No card computes its own freshness and no
// card is allowed to render data it could not date.
//
// Guardrail 5 in code form: three honest outcomes and no fourth.
//   error    -> we could not load or the envelope was malformed. The card says so. It never shows old data as new.
//   snapshot -> slo_seconds is null: this producer has no schedule. Show the age; never claim freshness.
//   fresh/stale -> age measured against the contract's own SLO.

const BASE = '/v2/data/';

export async function fetchContract(name) {
  const res = await fetch(BASE + encodeURIComponent(name) + '.json', { cache: 'no-store' });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const env = await res.json();
  if (!env || typeof env !== 'object' || Array.isArray(env)) throw new Error('not an object');
  if (!env._meta || typeof env._meta !== 'object') throw new Error('missing _meta');
  if (!('data' in env)) throw new Error('missing data');
  if (typeof env._meta.generated_at !== 'string') throw new Error('missing _meta.generated_at');
  return env;
}

export function freshness(meta, nowMs) {
  const gen = Date.parse(meta?.generated_at);
  if (!Number.isFinite(gen)) return { state: 'error', ageSeconds: null, reason: 'unparseable generated_at' };
  const ageSeconds = Math.max(0, (nowMs - gen) / 1000);
  const slo = meta.slo_seconds;
  if (slo === null || slo === undefined) return { state: 'snapshot', ageSeconds };
  return { state: ageSeconds > slo ? 'stale' : 'fresh', ageSeconds };
}

export function humanAge(sec) {
  if (sec === null || sec === undefined || !Number.isFinite(sec)) return '?';
  if (sec < 45) return 'just now';
  if (sec < 5400) return Math.round(sec / 60) + 'm ago';
  if (sec < 172800) return (sec / 3600).toFixed(1) + 'h ago';
  return (sec / 86400).toFixed(1) + 'd ago';
}

/** A single contract, self-refreshing. Instantiate once per card. */
export class Contract {
  env = $state(null);
  error = $state(null);
  loading = $state(true);

  constructor(name, refreshMs = 30000) {
    this.name = name;
    this.refreshMs = refreshMs;
  }

  get meta() { return this.env?._meta ?? null; }
  get data() { return this.env?.data ?? null; }

  async refresh() {
    try {
      this.env = await fetchContract(this.name);
      this.error = null;
    } catch (e) {
      // Keep the last good envelope so the card can say "last good data, N old" instead of going blank, but the
      // error is surfaced either way - a fetch failure is never rendered as success.
      this.error = String(e?.message ?? e);
    } finally {
      this.loading = false;
    }
  }

  /** Call once from an $effect; returns the teardown. */
  start() {
    this.refresh();
    const id = setInterval(() => this.refresh(), this.refreshMs);
    const onVis = () => { if (document.visibilityState === 'visible') this.refresh(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', onVis); };
  }
}

/** Shared 10s clock so every age badge counts up without each card owning a timer. */
export function clock() {
  let now = $state(Date.now());
  return {
    get now() { return now; },
    start() {
      const id = setInterval(() => { now = Date.now(); }, 10000);
      return () => clearInterval(id);
    }
  };
}
