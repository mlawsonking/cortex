<script>
  // Recommended for you - the ratings-seeded recommender's output (TMDB engine post-Trakt-pivot), each pick
  // carrying the films that produced it. Read-only: adding any of these is the Tonight's Pick path, not a
  // bulk button here.
  // Layout note (M3 feedback 2026-08-14): title and seed-list were one flex row, so a long "from" list
  // crushed the title to zero width. Title now owns its line; seeds are a clamped muted second line.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  function seeds(from) {
    const parts = String(from).split(', ');
    if (parts.length <= 3) return parts.join(', ');
    return parts.slice(0, 3).join(', ') + ' +' + (parts.length - 3) + ' more';
  }
</script>

<Card title="Recommended for you" {contract} {now}>
  {#snippet body(d)}
    {#each d.slice(0, 10) as r, i (r.tmdb ?? i)}
      <div class="rrow">
        <div class="rtitle">{r.title} <span class="muted">{r.year ?? ''}</span></div>
        {#if r.from}<div class="rfrom muted">from {seeds(r.from)}</div>{/if}
      </div>
    {:else}
      <div class="muted">the recommender has produced no picks</div>
    {/each}
  {/snippet}
</Card>

<style>
  .rrow { padding: 5px 0; border-top: 1px solid var(--line-soft); }
  .rrow:first-child { border-top: none; }
  .rtitle { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rfrom { font-size: var(--fs-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
