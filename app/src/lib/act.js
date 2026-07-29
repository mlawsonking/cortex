// act.js - the ONLY path from this app to a server action.
//
// The client is untrusted by design. It can do exactly one thing: POST a verb name that the server's own
// allow-list already accepts, carrying the short-lived HMAC nonce that dashboard-server.py injected into this
// page. It cannot construct new verbs, it never sees the /act secret, and no verb reachable from here can remove
// a torrent, unmonitor, or delete anything - the server refuses those regardless of what we send.
//
// The nonce is minted per 5-minute window, so a long-lived page eventually holds a stale one. On a 401 we re-read
// the nonce from a fresh copy of this page (the same mechanism that supplied it in the first place - no new
// endpoint, no new exposure) and retry exactly once. If that still fails, we say so rather than pretend.

function readNonce(doc = document) {
  return doc.querySelector('meta[name="act-nonce"]')?.getAttribute('content') ?? '';
}

let nonce = readNonce();

async function refreshNonce() {
  const res = await fetch('/v2/index.html', { cache: 'no-store' });
  if (!res.ok) throw new Error('nonce refresh HTTP ' + res.status);
  const html = await res.text();
  const m = html.match(/name="act-nonce"\s+content="([0-9a-f]{8,64})"/);
  if (!m) throw new Error('no nonce in refreshed page');
  nonce = m[1];
  return nonce;
}

async function post(verb, body) {
  return fetch('/act/' + verb, {
    method: 'POST',
    headers: { 'X-Act-Nonce': nonce, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body ?? ''
  });
}

/** Returns the server's plain-text reply. Throws with an honest message on failure. */
export async function act(verb, body) {
  let res = await post(verb, body);
  if (res.status === 401) {
    await refreshNonce();
    res = await post(verb, body);
  }
  const text = (await res.text()).trim();
  if (!res.ok) throw new Error(text || ('HTTP ' + res.status));
  if (text.startsWith('ERR')) throw new Error(text);
  return text;
}
