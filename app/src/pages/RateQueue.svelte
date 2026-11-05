<script>
  // Page "Rate" (#/rate) - clear the rating backlog fast. One title at a time, ranked by leverage (how much the
  // answer teaches Cortex). Rapid-fire: 1-10, Skip, Not me (household watched it), Bailed (gave up part-way).
  // Session cap of 10 so it never feels like homework; undo for every action (last 5 kept); the guess is revealed
  // only after he answers. Keyboard: 1-9, 0 = 10, s skip, n not me, b bailed, u undo, arrows browse.
  // Everything goes through /act/rate-title - the server re-checks the key (rate-queue or a live library lookup).
  import { clock } from '../lib/contracts.svelte.js';
  import Card from '../cards/Card.svelte';
  import RateRow from '../cards/RateRow.svelte';
  import { queue, rate, undo, search, stars } from '../lib/taste.svelte.js';
  import { actionsEnabled } from '../lib/act.js';

  const tick = clock();
  $effect(() => tick.start());
  // the rate-queue contract is polled once, app-wide, by App.svelte (nav badge + home card + this page)

  let gone = $state({});
  let cursor = $state(0);
  let session = $state(0);
  let capAck = $state(0);            // session count at which "keep going" was last pressed
  let moved = $state(0);
  let reveal = $state(null);         // {title, value, guess}
  let history = $state([]);          // newest first: {key, title, label, event_id, at}
  let err = $state('');
  let busy = $state(false);
  let showHH = $state(false);
  let q = $state('');
  let hits = $state([]);
  let searching = $state(false);
  let searchErr = $state('');
  let hitDone = $state({});

  const d = $derived(queue.data);
  const pool = $derived((d?.items ?? []).filter((r) => !gone[r.key]));
  const cur = $derived(pool.length ? pool[Math.min(cursor, pool.length - 1)] : null);
  const capped = $derived(d && session > 0 && session - capAck >= d.session_cap);

  function label(v) {
    return v === 'skip' ? 'skipped' : v === 'notme' ? 'not me' : v === 'bailed' ? 'bailed' : v + '/10';
  }

  async function answer(r, v) {
    if (!r || busy || !actionsEnabled) return;
    busy = true; err = '';
    gone[r.key] = true;
    try {
      const out = await rate(r.key, String(v), 'rate');
      history = [{ key: r.key, title: r.title, label: label(v), event_id: out.event_id, at: Date.now(), moves: r.terms?.moves ?? 0 },
                 ...history].slice(0, 5);
      if (v !== 'skip') { session += 1; moved += r.terms?.moves ?? 0; }
      if (typeof v === 'number') {
        reveal = { title: r.title, value: v, guess: out.guess };
        setTimeout(() => { if (reveal && reveal.title === r.title) reveal = null; }, 1600);
      }
      if (out.plex === 'failed') err = 'saved to Cortex; Plex did not take the star rating (it will not be lost)';
    } catch (e) {
      delete gone[r.key];
      err = "didn't save - " + String(e?.message ?? e).replace(/^ERR: /, '') + ' - try again';
    } finally {
      busy = false;
    }
  }

  async function undoOne(h) {
    if (busy) return;
    busy = true; err = '';
    try {
      await undo(h.key, h.event_id);
      delete gone[h.key];
      history = history.filter((x) => x.event_id !== h.event_id);
      if (h.label !== 'skipped') { session = Math.max(0, session - 1); moved = Math.max(0, moved - (h.moves || 0)); }
      const i = pool.findIndex((r) => r.key === h.key);
      if (i >= 0) cursor = i;
      reveal = null;
    } catch (e) {
      err = 'undo failed - ' + String(e?.message ?? e).replace(/^ERR: /, '');
    } finally {
      busy = false;
    }
  }

  function onKey(e) {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (capped && e.key !== 'u') return;
    const k = e.key;
    if (/^[0-9]$/.test(k) && cur) { e.preventDefault(); answer(cur, k === '0' ? 10 : Number(k)); }
    else if (k === 's' && cur) answer(cur, 'skip');
    else if (k === 'n' && cur) answer(cur, 'notme');
    else if (k === 'b' && cur && cur.completion !== null) answer(cur, 'bailed');
    else if (k === 'u' && history.length) undoOne(history[0]);
    else if (k === 'ArrowRight' && pool.length) cursor = (cursor + 1) % pool.length;
    else if (k === 'ArrowLeft' && pool.length) cursor = (cursor - 1 + pool.length) % pool.length;
  }
  $effect(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  let timer;
  function onSearch() {
    clearTimeout(timer);
    searchErr = '';
    if (q.trim().length < 2) { hits = []; return; }
    timer = setTimeout(async () => {
      searching = true;
      try { hits = await search(q.trim()); } catch (e) { searchErr = String(e?.message ?? e); hits = []; }
      finally { searching = false; }
    }, 300);
  }

  async function rateHit(h, v) {
    try {
      const out = await rate(h.key, String(v), 'search');
      hitDone[h.key] = v + '/10 saved' + (out.plex === 'failed' ? ' (Plex did not take the stars)' : '');
      gone[h.key] = true;
    } catch (e) {
      hitDone[h.key] = "didn't save - " + String(e?.message ?? e).replace(/^ERR: /, '');
    }
  }
</script>

<Card title="Rate what you watched" contract={queue} now={tick.now} span={true}>
  {#snippet body(d)}
    <div class="rp-head">
      <div>
        <div class="rp-prog"><strong>{Math.max(pool.length, d.backlog.total - d.items.filter((r) => gone[r.key]).length)}</strong> to go
          {#if session}<span class="muted"> &middot; {session} done this session</span>{/if}
          {#if d.backlog.streak_days}<span class="streak"> &middot; {d.backlog.streak_days}-day streak</span>{/if}</div>
        <div class="muted rp-sub">
          Cortex accuracy {d.eval.rho ?? '?'} (started at {d.eval.baseline_rho ?? '?'}{#if d.eval.live_mae !== null}; your last guesses were off by {d.eval.live_mae} on average{/if})
          {#if moved} &middot; this session's ratings touched {moved} of your picks{/if}
        </div>
      </div>
    </div>

    {#if !actionsEnabled}
      <div class="readonly-note">Rating is off: actions are switched off (wg\brain\ACTIONS-OFF).</div>
    {/if}

    {#if reveal}
      <div class="rp-reveal" aria-live="polite">{reveal.title}: you said <strong>{reveal.value}</strong>
        {#if reveal.guess} &middot; Cortex guessed <strong>{reveal.guess}</strong>
          {#if Math.abs(reveal.guess - reveal.value) >= 2}<span class="muted"> - learning from that</span>{/if}{/if}</div>
    {/if}

    {#if capped}
      <div class="rp-cap">
        <div class="rp-cap-t">Nice, {session} done.</div>
        <div class="muted">That is plenty for today. Come back any time - the queue keeps.</div>
        <button class="btn" onclick={() => (capAck = session)}>keep going</button>
      </div>
    {:else if cur}
      {#key cur.key}
      <article class="rp-card">
        <img class="rp-poster" alt="" src={'/photo?key=' + encodeURIComponent(cur.thumb) + '&width=300'} />
        <div class="rp-body">
          <div class="rp-title">{cur.title} <span class="muted">{cur.year ?? ''}</span>
            <span class="kind" class:tv={cur.type === 'tv'}>{cur.type === 'tv' ? 'show' : 'film'}</span></div>
          <div class="muted rp-meta">{cur.genres.join(' · ')}{#if cur.episodes} &middot; {cur.episodes}{/if}
            {#if cur.watched_at} &middot; last played {cur.watched_at}{/if}</div>
          <ul class="rp-reasons">{#each cur.reasons as w (w)}<li>{w}</li>{/each}</ul>
          {#if actionsEnabled}
            <RateRow title={cur.title} disabled={busy} onpick={(v) => answer(cur, v)} />
            <div class="rp-alt">
              <button class="btn ghost" disabled={busy} onclick={() => answer(cur, 'skip')} aria-label={'Skip ' + cur.title}>Skip</button>
              <button class="btn ghost" disabled={busy} onclick={() => answer(cur, 'notme')}
                      title="Someone else in the house watched this - Cortex will learn from it"
                      aria-label={cur.title + ' was not me'}>Not me</button>
              {#if cur.completion !== null}
                <button class="btn ghost" disabled={busy} onclick={() => answer(cur, 'bailed')}
                        title="You gave up on it - counts as half a dislike" aria-label={'I bailed on ' + cur.title}>Bailed</button>
              {/if}
              <span class="rp-browse">
                <button class="btn ghost" aria-label="previous title" onclick={() => (cursor = (cursor - 1 + pool.length) % pool.length)}>&larr;</button>
                <button class="btn ghost" aria-label="next title" onclick={() => (cursor = (cursor + 1) % pool.length)}>&rarr;</button>
              </span>
            </div>
          {/if}
          {#if err}<div class="act-msg err">{err}</div>{/if}
        </div>
      </article>
      {/key}
      <div class="muted rp-keys">keys: 1-9, 0 = 10 &middot; s skip &middot; n not me &middot; b bailed &middot; u undo &middot; &larr; &rarr; browse</div>
    {:else}
      <div class="rp-done">All caught up - nothing left to rate. <span class="muted">New watches show up here overnight.</span></div>
    {/if}

    {#if history.length}
      <div class="rp-hist">
        {#each history as h, i (h.event_id)}
          <span class="rp-h" class:fresh={i === 0 && tick.now - h.at < 10000}>
            {h.title}: {h.label}
            <button class="linkbtn" disabled={busy} onclick={() => undoOne(h)} aria-label={'Undo ' + h.label + ' for ' + h.title}>undo</button>
          </span>
        {/each}
      </div>
    {/if}

    <div class="rp-search">
      <input type="search" placeholder="rate anything in your library..." bind:value={q} oninput={onSearch}
             aria-label="Search your library to rate a title" />
      {#if searching}<span class="muted">searching...</span>{/if}
      {#if searchErr}<span class="act-msg err">{searchErr}</span>{/if}
      {#each hits as h (h.key)}
        <div class="rp-hit">
          <div class="rp-hit-t">{h.title} <span class="muted">{h.year ?? ''} &middot; {h.type === 'tv' ? 'show' : 'film'}</span>
            {#if h.rating !== null && !hitDone[h.key]}<span class="muted"> &middot; rated {h.rating} {stars(h.rating)}</span>{/if}</div>
          {#if hitDone[h.key]}<div class="muted">{hitDone[h.key]}</div>
          {:else if !h.rateable}<div class="muted">Plex has no TMDB id for this one - cannot rate it reliably</div>
          {:else if actionsEnabled}<RateRow title={h.title} onpick={(v) => rateHit(h, v)} />{/if}
        </div>
      {/each}
    </div>

    <div class="rp-hh">
      <button class="linkbtn" onclick={() => (showHH = !showHH)}>
        {d.backlog.household_hidden} household plays hidden &middot; {showHH ? 'hide' : 'show'}</button>
      {#if showHH}
        <div class="muted rp-sub">Kids titles, and plays whose device and time of day look like the household. If one is
          yours, rate it here and Cortex learns.</div>
        {#each d.household.filter((r) => !gone[r.key]) as r (r.key)}
          <div class="rp-hit">
            <div class="rp-hit-t">{r.title} <span class="muted">{r.year ?? ''} &middot; {r.reasons[0]}</span></div>
            {#if actionsEnabled}<RateRow title={r.title} onpick={(v) => answer(r, v)} />{/if}
          </div>
        {/each}
      {/if}
    </div>
    <div class="muted" style:margin-top="12px">{d.note}</div>
  {/snippet}
</Card>

<style>
  .rp-head { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .rp-prog { font-size: var(--fs-lg); color: var(--text-strong); }
  .streak { color: var(--warn); }
  .rp-sub { font-size: var(--fs-xs); margin-top: 2px; }
  .readonly-note { color: var(--warn); margin-bottom: 10px; }
  .rp-reveal { padding: 10px 12px; border-radius: var(--r); background: var(--ok-tint);
               border: 1px solid var(--ok-line); margin-bottom: 10px; color: var(--text-strong); }
  .rp-card { display: flex; gap: 16px; padding: 12px; border: 1px solid var(--line); border-radius: var(--r);
             background: var(--surface-2); }
  .rp-poster { width: 150px; height: 225px; max-height: 40vh; flex: 0 0 auto; object-fit: cover; border-radius: var(--r-sm);
               background: var(--bg-sunken); border: 1px solid var(--line); }
  .rp-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .rp-title { font-size: var(--fs-lg); font-weight: 700; color: var(--text-strong); }
  .rp-meta { font-size: var(--fs-xs); }
  .rp-reasons { margin: 0; padding-left: 18px; font-size: var(--fs-sm); }
  .rp-alt { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .rp-alt .btn { min-height: 40px; }
  .rp-browse { margin-left: auto; display: flex; gap: 4px; }
  .rp-keys { font-size: var(--fs-xs); margin-top: 6px; }
  .rp-cap { padding: 22px; text-align: center; border: 1px dashed var(--line); border-radius: var(--r); }
  .rp-cap-t { font-size: var(--fs-lg); color: var(--text-strong); margin-bottom: 4px; }
  .rp-cap .btn { margin-top: 10px; }
  .rp-done { padding: 16px 0; }
  .rp-hist { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .rp-h { font-size: var(--fs-xs); padding: 4px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--text-dim); }
  .rp-h.fresh { border-color: var(--info); color: var(--text-strong); }
  .linkbtn { background: none; border: 0; color: var(--info); cursor: pointer; padding: 0 2px; font: inherit; }
  .linkbtn:disabled { opacity: 0.5; }
  .rp-search { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
  .rp-search input { width: 100%; box-sizing: border-box; min-height: 40px; padding: 8px 10px; border-radius: var(--r-sm);
                     border: 1px solid var(--line); background: var(--bg-sunken); color: var(--text-strong); font: inherit; }
  .rp-hit { padding: 8px 0; border-top: 1px solid var(--line-soft); display: flex; flex-direction: column; gap: 4px; }
  .rp-hit-t { font-weight: 600; color: var(--text-strong); }
  .rp-hh { margin-top: 16px; }
  .kind { font-size: var(--fs-xs); font-weight: 500; padding: 1px 6px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--text-dim); margin-left: 4px; vertical-align: 3px; }
  .kind.tv { color: var(--accent); border-color: var(--accent-line); }
  @media (max-width: 640px) {
    .rp-card { flex-direction: column; align-items: center; padding: 10px; }
    .rp-poster { width: 120px; height: 180px; }
    .rp-body { width: 100%; }
  }
</style>
