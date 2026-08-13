<script>
  // I3 Dead Shelf - curation debt made visible. Films deliberately curated in, then never played and never
  // rated, aging on the shelf. READ-ONLY BY CONSTRUCTION: the gameplan sketches spotlight / park /
  // exclude-from-recs verbs for this card, but none of them exist server-side and a new verb needs its own
  // mini security review plus Michael's approval (post-M3) before any button may appear here.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  // shelf age reads in days until a year of it has passed, then in years - "1.4y" lands harder than "511d"
  function age(days) {
    return days > 365 ? (days / 365).toFixed(1) + 'y' : days + 'd';
  }
</script>

<Card title="Dead shelf" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="stats" style:margin-bottom="10px">
      <div class="stat accent"><div class="n">{d.dead_total}</div><div class="l">never touched &gt; 60d</div></div>
      <div class="stat"><div class="n">{d.dead_pct.toFixed(1)}%</div><div class="l">of the {d.pool_total} unwatched</div></div>
      <div class="stat"><div class="n">{d.buckets.over_365.count}</div><div class="l">over a year old</div></div>
      <div class="stat"><div class="n dim">{d.settling}</div><div class="l">still settling (&lt; 60d)</div></div>
    </div>

    <div class="row" style:margin-bottom="10px" style:flex-wrap="wrap">
      <span class="muted">2-6 months <strong>{d.buckets.d60_180.count}</strong></span>
      <span class="muted">6-12 months <strong>{d.buckets.d180_365.count}</strong></span>
      <span class="muted">over a year <strong>{d.buckets.over_365.count}</strong></span>
    </div>

    <div class="muted" style:margin-bottom="6px">
      Longest on the shelf &mdash; curated in, never played, never rated:
    </div>
    {#each d.oldest as m (m.ratingKey ?? m.title)}
      <div class="li">
        <span class="li-main">{m.title} <span class="muted">{m.year ?? ''}</span></span>
        <span class="li-side">{age(m.days)}{#if m.gb != null} &middot; {m.gb.toFixed(1)} GB{/if}
          {#if m.genres.length} &middot; {m.genres.join(', ')}{/if}</span>
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      showing {d.oldest.length} of {d.dead_total} &middot; pool is never-watched, never-rated, 1987 or later
      {#if d.unknown_age}&middot; {d.unknown_age} undateable (added-date not trustworthy, excluded){/if}
      &middot; read-only: park / exclude verbs need their own review before buttons appear here
    </div>
  {/snippet}
</Card>
