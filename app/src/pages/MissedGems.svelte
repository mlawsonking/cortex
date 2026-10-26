<script>
  // Page 2 "Missed Gems" (#/missed) - michael's OWN library, owned and never played, ranked by taste. Weekly,
  // deterministic (no model). Read-only: no verb hangs off this page; posters come through the existing
  // same-origin /photo proxy (Plex token never reaches the browser).
  import { Contract, clock } from '../lib/contracts.svelte.js';
  import Card from '../cards/Card.svelte';

  const tick = clock();
  const mg = new Contract('missed-gems', 300000);
  $effect(() => tick.start());
  $effect(() => mg.start());

  function shelf(days) {
    if (days === null || days === undefined) return 'added ?';
    if (days < 1) return 'landed today';
    if (days === 1) return '1 day on the shelf';
    if (days < 60) return days + ' days on the shelf';
    if (days < 730) return Math.round(days / 30) + ' months on the shelf';
    return (days / 365).toFixed(1) + ' years on the shelf';
  }
</script>

{#snippet rows(list, shame)}
  <div class="mg-grid">
    {#each list as r (r.key)}
      <article class="mg-item">
        {#if r.thumb}
          <img class="mg-poster" loading="lazy" alt="" src={'/photo?key=' + encodeURIComponent(r.thumb) + '&width=150'} />
        {:else}
          <div class="mg-poster"></div>
        {/if}
        <div class="mg-body">
          <div class="mg-title">{r.title} <span class="muted">{r.year ?? ''}</span>
            <span class="kind" class:tv={r.type === 'tv'}>{r.type === 'tv' ? 'show' : 'film'}</span></div>
          <div class="muted mg-meta">{r.genres.join(' · ')}{#if r.episodes} &middot; {r.episodes} episodes{/if}</div>
          <div class="match">
            <div class="bar"><div class="bar-fill" style:width={Math.round(r.match * 100) + '%'}></div></div>
            <span class="mono">{Math.round(r.match * 100)}%</span>
          </div>
          {#if r.because.length}<div class="because">because you loved {r.because.join(', ')}</div>{/if}
          {#if r.people.length}<div class="muted mg-meta">with {r.people.join(', ')}</div>{/if}
          <div class="shelf-age" class:shame={shame && r.days_on_shelf > 180}>{shelf(r.days_on_shelf)}</div>
        </div>
      </article>
    {:else}
      <div class="muted">nothing here this week</div>
    {/each}
  </div>
{/snippet}

<Card title="Missed Gems" contract={mg} now={tick.now} span={true}>
  {#snippet body(d)}
    <div class="lede">Already on your shelf, never played, and very much your kind of thing.</div>
    <div class="muted" style:margin-bottom="14px">
      {d.counts.scored - d.counts.shows_pool} unwatched films and {d.counts.shows_pool} unwatched series considered
      &middot; {d.tv_source}
    </div>

    <h3 class="sec">Landed recently <span class="muted">added in the last {d.landed_days} days</span></h3>
    {@render rows(d.landed, false)}

    <h3 class="sec">This is you. Why you no watch yet? <span class="muted">the all-time best unwatched fits</span></h3>
    {@render rows(d.gems, true)}

    <h3 class="sec">Shows you haven't started <span class="muted">top {(d.shows ?? []).length} of {d.counts.shows_pool} unwatched series by match</span></h3>
    {#if d.shows}{@render rows(d.shows, true)}{:else}<div class="muted">this contract predates the shows section (v1.0.0) - it appears after the next weekly run</div>{/if}

    <div class="muted" style:margin-top="12px">{d.note}</div>
  {/snippet}
</Card>

<style>
  .lede { margin-bottom: 2px; }
  .sec { font-size: 15px; color: var(--text-strong); margin: 14px 0 10px; font-weight: 600; }
  .sec .muted { font-weight: 400; margin-left: 6px; }
  .mg-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
  .mg-item { display: flex; gap: 12px; padding: 9px; border: 1px solid var(--line-soft); border-radius: var(--r);
             background: rgba(255, 255, 255, 0.015); min-width: 0; }
  .mg-poster { width: 64px; height: 96px; flex: 0 0 auto; object-fit: cover; border-radius: var(--r-sm);
               background: var(--bg-sunken); border: 1px solid var(--line); }
  .mg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .mg-title { font-weight: 600; color: var(--text-strong); }
  .mg-meta { font-size: 11px; }
  .kind { font-size: 9px; text-transform: uppercase; letter-spacing: 0.8px; padding: 1px 6px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--text-dim); margin-left: 4px; vertical-align: 2px; }
  .kind.tv { color: var(--accent); border-color: rgba(188, 140, 255, 0.35); }
  .match { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-dim); }
  .match .bar { flex: 1; max-width: 140px; }
  .because { font-size: 12px; }
  .shelf-age { font-size: 11px; color: var(--text-faint); }
  .shelf-age.shame { color: var(--warn); }
  @media (max-width: 640px) { .mg-grid { grid-template-columns: 1fr; } }
</style>
