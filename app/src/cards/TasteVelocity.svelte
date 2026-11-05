<script>
  // I7 Taste Velocity - what is heating up and what is cooling off in this household's viewing. Each row is one
  // genre's share of plays in the rolling 90-day window against its share across the whole Plex history; the bar
  // diverges from a centre line, right/up-arrow for heating, left/down-arrow for cooling.
  //
  // READ-ONLY BY CONSTRUCTION, and deliberately opinion-free about what to DO with a heating lane: turning
  // "Mystery is up" into "so go add Mysteries" is a recommendation, which belongs to the recs contract and its own
  // review - not to a chart that is only allowed to describe.
  //
  // The note is rendered in full, never truncated. It is where the sample size, the shared-account caveat (the
  // kids' viewing is inside these numbers) and the unmapped-title count live, and a delta read without them is a
  // number that lies by omission.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  const rows = $derived.by(() => {
    const g = contract.data?.genres ?? [];
    return [...g].sort((a, b) => b.delta - a.delta);   // heating on top, cooling at the bottom
  });

  const maxAbs = $derived.by(() => {
    let m = 0.001;
    for (const r of rows) if (Math.abs(r.delta) > m) m = Math.abs(r.delta);
    return m;
  });

  const heating = $derived(rows.filter((r) => r.delta > 0).length);
  const cooling = $derived(rows.filter((r) => r.delta < 0).length);

  const pct = (x) => (x * 100).toFixed(1) + '%';
  const signed = (x) => (x > 0 ? '+' : x < 0 ? '-' : '') + (Math.abs(x) * 100).toFixed(1) + '%';
  const width = (x) => (Math.abs(x) / maxAbs) * 50 + '%';   // half the track is 100% of the largest move
</script>

<Card title="Taste velocity" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="stats" style:margin-bottom="12px">
      <div class="stat accent"><div class="n">{heating}</div><div class="l">genres heating</div></div>
      <div class="stat"><div class="n dim">{cooling}</div><div class="l">genres cooling</div></div>
      <div class="stat"><div class="n">{d.plays_recent}</div><div class="l">plays in {d.window_days}d</div></div>
      <div class="stat"><div class="n dim">{d.plays_lifetime}</div><div class="l">plays lifetime</div></div>
    </div>

    {#if rows.length === 0}
      <div class="muted">no genre cleared the noise floor &mdash; nothing honest to plot</div>
    {:else}
      {#each rows as r (r.genre)}
        <div class="tv-row">
          <span class="tv-name">
            <span class="tv-arrow" class:up={r.delta > 0} class:down={r.delta < 0}>
              {#if r.delta > 0}&#9650;{:else if r.delta < 0}&#9660;{:else}&#8226;{/if}
            </span>
            {r.genre}
          </span>
          <span class="tv-track" title="{r.genre}: {pct(r.recent_share)} of the last {d.window_days} days vs {pct(r.lifetime_share)} lifetime">
            <span class="tv-mid"></span>
            {#if r.delta > 0}
              <span class="tv-fill up" style:left="50%" style:width={width(r.delta)}></span>
            {:else if r.delta < 0}
              <span class="tv-fill down" style:right="50%" style:width={width(r.delta)}></span>
            {/if}
          </span>
          <span class="tv-delta" class:up={r.delta > 0} class:down={r.delta < 0}>{signed(r.delta)}</span>
          <span class="tv-shares mono">{pct(r.recent_share)} <span class="tv-vs">vs</span> {pct(r.lifetime_share)}</span>
        </div>
      {/each}
      <div class="muted" style:margin-top="8px">
        90-day share <span class="tv-vs">vs</span> lifetime share, per genre &middot; showing {rows.length} lanes by
        size of move
      </div>
    {/if}

    <div class="muted tv-note">{d.note}</div>
  {/snippet}
</Card>

<style>
  .tv-row {
    display: grid;
    grid-template-columns: 132px 1fr 62px 118px;
    align-items: center;
    gap: 10px;
    padding: 3px 0;
    font-size: var(--fs-sm);
  }
  .tv-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tv-arrow { font-size: var(--fs-xs); color: var(--text-faint); }
  .tv-arrow.up { color: var(--ok); }
  .tv-arrow.down { color: var(--warn); }

  .tv-track {
    position: relative;
    display: block;
    height: 10px;
    background: var(--bg-sunken);
    border: 1px solid var(--line-soft);
    border-radius: var(--r-sm);
    overflow: hidden;
  }
  .tv-mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--line); }
  .tv-fill { position: absolute; top: 0; bottom: 0; transition: width 0.4s ease; }
  .tv-fill.up { background: linear-gradient(90deg, var(--ok-soft), var(--ok)); border-radius: 0 3px 3px 0; }
  .tv-fill.down { background: linear-gradient(90deg, var(--warn), var(--warn-soft)); border-radius: 3px 0 0 3px; }

  .tv-delta { text-align: right; font-variant-numeric: tabular-nums; font-size: var(--fs-xs); color: var(--text-dim); }
  .tv-delta.up { color: var(--ok); }
  .tv-delta.down { color: var(--warn); }

  .tv-shares { text-align: right; font-size: var(--fs-xs); color: var(--text-faint); }
  .tv-vs { color: var(--text-faint); font-style: italic; }

  .tv-note { margin-top: 10px; line-height: 1.55; }

  @media (max-width: 720px) {
    .tv-row { grid-template-columns: 96px 1fr 56px; }
    .tv-shares { display: none; }
  }
</style>
