<script>
  import Card from './Card.svelte';
  import { count, bytes } from '../lib/fmt.js';

  let { contract, now } = $props();
</script>

<Card title="Library" {contract} {now}>
  {#snippet body(d)}
    <div class="stats">
      <div class="stat accent"><div class="n">{count(d.plex.movies)}</div><div class="l">Movies (Plex)</div></div>
      <div class="stat"><div class="n">{count(d.plex.tv)}</div><div class="l">TV shows</div></div>
      <div class="stat"><div class="n">{count(d.rated)}</div><div class="l">Rated</div></div>
    </div>
    <div class="muted" style:margin-top="12px">
      Radarr tracks {count(d.radarr.total)} movies
      &mdash; {count(d.radarr.have)} downloaded, {count(d.radarr.monitored_missing)} wanted
      {#if d.radarr.size_bytes !== null}&middot; {bytes(d.radarr.size_bytes)} on disk{/if}
    </div>
    <div class="muted">
      Sonarr {count(d.sonarr.series)} series ({count(d.sonarr.monitored)} monitored)
      {#if d.sonarr.missing_episodes !== null}&middot; {count(d.sonarr.missing_episodes)} episodes missing{/if}
    </div>
  {/snippet}
</Card>
