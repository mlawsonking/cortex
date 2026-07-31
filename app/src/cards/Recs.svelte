<script>
  // Recommended for you - the Trakt-seeded recommender's output, each pick carrying the film that produced it.
  // Read-only: adding any of these is the Tonight's Pick / passport path, not a bulk button here.
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="Recommended for you" {contract} {now}>
  {#snippet body(d)}
    {#each d.slice(0, 10) as r, i (r.tmdb ?? i)}
      <div class="li">
        <span class="li-main">{r.title} <span class="muted">{r.year ?? ''}</span></span>
        <span class="li-side">{r.from ? 'from ' + r.from : ''}</span>
      </div>
    {:else}
      <div class="muted">the recommender has produced no picks</div>
    {/each}
  {/snippet}
</Card>
