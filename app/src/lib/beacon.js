// beacon.js - P6 "bug loop", client half. Side-effect module: importing it installs two global listeners and
// nothing else. It exports nothing and touches no app state, so no card can depend on it and it can be deleted
// in one line if it ever misbehaves.
//
// WHAT IT SENDS: an uncaught error or an unhandled promise rejection becomes ONE small JSON POST to /beacon
// (same origin, so the /v2 CSP's connect-src 'self' already allows it), carrying the same short-lived HMAC nonce
// that act.js uses. The server is tailnet-gated, rate-limited and only alerts on a signature it has never seen.
//
// WHAT IT WILL NOT DO:
//   - never throw. A reporting layer that can itself fail loudly is worse than no reporting layer. Every path is
//     wrapped, the fetch is fire-and-forget, and a re-entry guard stops an error inside this file from looping.
//   - never spam. Same signature (msg + src + line) is sent at most ONCE per page session, and a page session
//     sends at most 5 beacons total. Both counters are in-memory: a reload legitimately starts a fresh session.
//   - never send user content. Only the error text, script path, line, stack and (server-side) the User-Agent.
//
// The nonce handling deliberately MIRRORS act.js (read the meta tag; on 401 re-read a fresh copy of the page and
// retry exactly once) instead of importing from it: act.js does not export its nonce, and this file must stay
// standalone so it cannot drag the action layer into an error path.

const ENDPOINT = '/beacon';
const MAX_PER_SESSION = 5;
const CAP = { msg: 300, src: 200, stack: 800 };

const seen = new Set();
let sent = 0;
let busy = false; // re-entry guard: an error raised while reporting must not report itself
let nonce = document.querySelector('meta[name="act-nonce"]')?.getAttribute('content') ?? '';

function clip(value, max) {
  if (value === null || value === undefined) return '';
  const s = typeof value === 'string' ? value : String(value);
  return s.slice(0, max);
}

// Strip the origin so the same bug does not get two signatures just because the page was opened by tailnet IP
// on the phone and by 127.0.0.1 on the server.
function shortSrc(src) {
  try {
    return clip(new URL(src, window.location.href).pathname, CAP.src);
  } catch {
    return clip(src, CAP.src);
  }
}

async function refreshNonce() {
  const res = await fetch('/v2/index.html', { cache: 'no-store' });
  if (!res.ok) throw new Error('nonce refresh HTTP ' + res.status);
  const m = (await res.text()).match(/name="act-nonce"\s+content="([0-9a-f]{8,64})"/);
  if (!m) throw new Error('no nonce in refreshed page');
  nonce = m[1];
}

function post(body) {
  return fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'X-Act-Nonce': nonce, 'Content-Type': 'application/json' },
    body,
    keepalive: true // survives the page being closed right after the error
  });
}

async function send(payload) {
  const body = JSON.stringify(payload);
  let res = await post(body);
  if (res.status === 401) {
    // The nonce is minted per 5-minute window; a page left open all afternoon holds a dead one.
    await refreshNonce();
    res = await post(body);
  }
  return res;
}

function report(msg, src, line, stack) {
  if (busy) return;
  busy = true;
  try {
    const m = clip(msg, CAP.msg);
    if (!m) return;
    const s = shortSrc(src);
    const l = Number.isFinite(line) ? Math.trunc(line) : 0;
    const key = m + '|' + s + '|' + l;
    if (seen.has(key)) return; // this exact fault already reported this session
    if (sent >= MAX_PER_SESSION) return; // hard cap: a render loop cannot turn into a POST flood
    seen.add(key);
    sent += 1; // counted on ATTEMPT, so a failing server cannot be retried into a storm
    send({ msg: m, src: s, line: l, stack: clip(stack, CAP.stack) }).catch(() => {});
  } catch {
    // reporting is best-effort by definition
  } finally {
    busy = false;
  }
}

window.addEventListener('error', (e) => {
  try {
    report(e?.message || 'script error', e?.filename || '', e?.lineno ?? 0, e?.error?.stack || '');
  } catch {}
});

window.addEventListener('unhandledrejection', (e) => {
  try {
    const r = e?.reason;
    const msg = r instanceof Error ? r.message : typeof r === 'string' ? r : 'unhandled rejection';
    report(msg || 'unhandled rejection', 'unhandledrejection', 0, r instanceof Error ? r.stack || '' : '');
  } catch {}
});
