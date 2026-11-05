<script>
  // Page 1 "Streaming Best" (#/streaming) - what is new or peaking across streaming, quality-floored, ranked by
  // fit to michael's taste. Monthly. Everything shown comes from the streaming-best contract; posters are the
  // producer's same-origin /art/ cache (CSP stays img-src 'self'). The add buttons are the only disk-spending
  // verbs in the app - see AddBtn.svelte for what the server re-checks.
  import { Contract, clock } from '../lib/contracts.svelte.js';
  import Card from '../cards/Card.svelte';
  import AddBtn from '../cards/AddBtn.svelte';
  import { actionsEnabled } from '../lib/act.js';
  import ThumbBtns from '../cards/ThumbBtns.svelte';
  import { ledger, thumb, thumbOf } from '../lib/taste.svelte.js';

  const tick = clock();
  const sb = new Contract('streaming-best', 300000);
  $effect(() => tick.start());
  $effect(() => sb.start());
  $effect(() => ledger.start());          // thumbs state (taste loop): a thumbs-down row collapses with an undo

  let filter = $state('all');

  function airingText(a) {
    if (!a) return '';
    if (a.next_air_date) return 'next episode ' + a.next_air_date;
    if (a.status === 'Ended' || a.status === 'Canceled') return a.status.toLowerCase() + (a.seasons ? ' · ' + a.seasons + ' season' + (a.seasons > 1 ? 's' : '') : '');
    return (a.status || 'airing').toLowerCase() + (a.seasons ? ' · ' + a.seasons + ' season' + (a.seasons > 1 ? 's' : '') : '');
  }
</script>

<Card title="Streaming Best" contract={sb} now={tick.now} span={true}>
  {#snippet body(d)}
    <div class="lede">
      The best of what is new on streaming, filtered hard for quality and ranked by how much it is <em>you</em>.
      <span class="muted">{d.month} &middot; window {d.window_start} &rarr; {d.window_end} &middot;
        {d.pool.candidates} titles considered, {d.pool.survivors} cleared the floors</span>
    </div>
    <div class="ai" class:fallback={!d.ai}>
      {#if d.ai}curated + annotated by Claude (subscription) from a {d.pool.shortlist}-title taste shortlist
      {:else}deterministic taste order &mdash; {d.ai_note}{/if}
    </div>
    {#if !actionsEnabled}
      <div class="muted" style:margin-bottom="8px">add buttons hidden: actions are switched off (wg\brain\ACTIONS-OFF)</div>
    {/if}

    <div class="tabs">
      {#each [['all', 'All'], ['movie', 'Films'], ['tv', 'Shows']] as [k, label] (k)}
        <button class="btn ghost" class:on={filter === k} onclick={() => (filter = k)}>
          {label} <span class="muted">{k === 'all' ? d.items.length : d.items.filter((x) => x.type === k).length}</span>
        </button>
      {/each}
    </div>

    <div class="sb-grid">
      {#each d.items.filter((x) => filter === 'all' || x.type === filter) as r (r.key)}
        {#if thumbOf(r.type + ':' + r.tmdb_id) === 'down'}
        <article class="sb-item gone"><span class="muted">{r.title} hidden - not for you.</span>
          <button class="linkbtn" onclick={() => thumb(r.type + ':' + r.tmdb_id, 'clear').catch(() => {})}>undo</button></article>
        {:else}
        <article class="sb-item">
          {#if r.poster_local}
            <img class="sb-poster" loading="lazy" alt="" src={r.poster_local} />
          {:else}
            <div class="sb-poster none">{r.type === 'tv' ? 'TV' : 'FILM'}</div>
          {/if}
          <div class="sb-body">
            <div class="sb-title">
              <span class="rank">{r.rank}</span> {r.title} <span class="muted">{r.year ?? ''}</span>
              <span class="kind" class:tv={r.type === 'tv'}>{r.type === 'tv' ? 'show' : 'film'}</span>
            </div>
            <div class="sb-meta muted">
              {r.genres.join(' · ')} &middot; TMDB {r.vote_avg.toFixed(1)} ({r.votes.toLocaleString()})
              {#if r.airing} &middot; {airingText(r.airing)}{/if}
            </div>
            <div class="match">
              <div class="bar"><div class="bar-fill" style:width={Math.round(r.match * 100) + '%'}></div></div>
              <span class="mono">{Math.round(r.match * 100)}%</span>
            </div>
            <div class="why">{r.why}</div>
            {#if r.because.length}<div class="because muted">because you loved {r.because.join(', ')}</div>{/if}
            {#if r.people.length}<div class="because muted">with {r.people.join(', ')}</div>{/if}
            <details class="ov"><summary class="muted">synopsis</summary><p>{r.overview || 'no synopsis on TMDB'}</p></details>
            <div class="sb-act"><AddBtn type={r.type} tmdb={r.tmdb_id} /> <ThumbBtns tkey={r.type + ':' + r.tmdb_id} title={r.title} /></div>
          </div>
        </article>
        {/if}
      {/each}
    </div>
    <div class="muted" style:margin-top="12px">{d.note}</div>
  {/snippet}
</Card>

<style>
  .lede { margin-bottom: 6px; }
  .lede .muted { display: block; margin-top: 2px; }
  .ai { font-size: var(--fs-xs); color: var(--accent); margin-bottom: 10px; }
  .ai.fallback { color: var(--warn); }
  .tabs { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .tabs .on { border-color: var(--info); color: var(--text-strong); }
  .sb-item.gone { padding: 10px 12px; align-items: center; gap: 8px; }
  .linkbtn { background: none; border: 0; color: var(--info); cursor: pointer; padding: 0 2px; font: inherit; }
  .sb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
  .sb-item { display: flex; gap: 12px; padding: 10px; border: 1px solid var(--line-soft); border-radius: var(--r);
             background: var(--surface-2); min-width: 0; }
  .sb-poster { width: 78px; height: 117px; flex: 0 0 auto; object-fit: cover; border-radius: var(--r-sm);
               background: var(--bg-sunken); border: 1px solid var(--line); }
  .sb-poster.none { display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: var(--fs-xs); }
  .sb-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .sb-title { font-weight: 600; color: var(--text-strong); }
  .rank { color: var(--text-faint); font-variant-numeric: tabular-nums; margin-right: 2px; }
  .kind { font-size: var(--fs-xs); font-weight: 500; padding: 1px 6px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--text-dim); margin-left: 4px; vertical-align: 2px; }
  .kind.tv { color: var(--accent); border-color: var(--accent-line); }
  .sb-meta { font-size: var(--fs-xs); }
  .match { display: flex; align-items: center; gap: 8px; font-size: var(--fs-xs); color: var(--text-dim); }
  .match .bar { flex: 1; max-width: 160px; }
  .why { font-size: var(--fs-sm); }
  .because { font-size: var(--fs-xs); }
  .ov summary { cursor: pointer; font-size: var(--fs-xs); }
  .ov p { font-size: var(--fs-xs); color: var(--text-dim); margin-top: 3px; }
  .sb-act { margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  @media (max-width: 640px) { .sb-grid { grid-template-columns: 1fr; } }
</style>
