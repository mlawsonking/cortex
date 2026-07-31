<script>
  // Ask & mood. Both hit existing GET endpoints that run a claude -p runner server-side on the Claude Code
  // SUBSCRIPTION - never the metered API - and are tailnet-gated and debounced by the server. Strictly
  // PROPOSAL-ONLY: they answer "do we own this" / "what should we watch", and nothing they return downloads,
  // monitors or mutates anything.
  //
  // They are nonetheless gated on the ACTIONS-OFF kill-flag. They mutate nothing, but they DO cause the server to
  // execute a model query, and "read-only mode" that still triggers work on the box would make the banner's claim
  // false. When the flag is set this page renders cached contracts and nothing else.
  import { actionsEnabled } from '../lib/act.js';

  let query = $state('');
  let asking = $state(false);
  let answer = $state(null);
  let askErr = $state('');

  let mood = $state('');
  let mooding = $state(false);
  let picks = $state([]);
  let moodErr = $state('');

  async function runAsk(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    asking = true; answer = null; askErr = '';
    try {
      const r = await fetch('/ask?q=' + encodeURIComponent(q), { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      if (j._err) askErr = j._err; else answer = j;
    } catch (ex) {
      askErr = String(ex?.message ?? ex);
    } finally {
      asking = false;
    }
  }

  async function runMood(e) {
    e.preventDefault();
    const q = mood.trim();
    if (!q) return;
    mooding = true; picks = []; moodErr = '';
    try {
      const r = await fetch('/mood?q=' + encodeURIComponent(q), { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      if (j._err) moodErr = j._err; else picks = j.picks ?? [];
    } catch (ex) {
      moodErr = String(ex?.message ?? ex);
    } finally {
      mooding = false;
    }
  }

  const VERDICT = { own: 'var(--ok)', stream: 'var(--info)' };
</script>

<section class="card">
  <div class="card-head"><h2 class="card-title">Ask &amp; mood</h2></div>

  {#if !actionsEnabled}
    <div class="muted">disabled in read-only mode &mdash; these run a model query on the server</div>
  {:else}
  <form onsubmit={runAsk}>
    <input class="field" bind:value={query} autocomplete="off" placeholder="that one where he relives the same day..." />
    <button class="btn" style:margin-top="6px" type="submit" disabled={asking}>{asking ? 'thinking...' : 'ask the catalog'}</button>
  </form>
  {#if askErr}
    <div class="act-msg err" style:margin-top="6px">{askErr}</div>
  {:else if answer}
    <div style:margin-top="8px">
      <strong>{answer.match ?? 'no match'}</strong>
      {#if answer.verdict}
        <span style:color={VERDICT[answer.verdict] ?? 'var(--warn)'} style:font-weight="700"> {answer.verdict.toUpperCase()}</span>
      {/if}
      {#if answer.why}<div class="muted">{answer.why}</div>{/if}
    </div>
  {/if}

  <form onsubmit={runMood} style:margin-top="14px">
    <input class="field" bind:value={mood} autocomplete="off" placeholder="something short and funny" />
    <button class="btn" style:margin-top="6px" type="submit" disabled={mooding}>{mooding ? 'thinking...' : 'set the mood'}</button>
  </form>
  {#if moodErr}
    <div class="act-msg err" style:margin-top="6px">{moodErr}</div>
  {:else if picks.length}
    {#each picks as p, i (p.title + i)}
      <div class="li">
        <span class="li-main"><strong>{p.title}</strong> <span class="muted">{p.year ?? ''}</span>
          {#if p.why}<div class="muted">{p.why}</div>{/if}
        </span>
      </div>
    {/each}
  {/if}
  {/if}

  <div class="muted" style:margin-top="8px">owned-first &middot; proposal-only &middot; nothing is downloaded</div>
</section>
