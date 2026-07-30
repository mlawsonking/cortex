<script>
  // Posters come through the EXISTING same-origin /photo proxy, so the Plex token never reaches the browser and
  // the strict CSP (img-src 'self') is satisfied without an exception.
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="Now playing" {contract} {now}>
  {#snippet body(d)}
    {#if !d.ok}
      <div class="state err">Plex streaming-path probe FAILED</div>
      <div class="muted">identity/sections did not answer &mdash; this is a real probe, not a port check</div>
    {/if}

    {#each d.sessions as s (s.title + s.user)}
      <div class="np">
        {#if s.thumb}
          <img class="np-art" loading="lazy" alt="" src={'/photo?key=' + encodeURIComponent(s.thumb) + '&width=80'} />
        {/if}
        <div class="np-body">
          <div class="li-main">{s.title} <span class="muted">&mdash; {s.user}</span></div>
          <div class="bar" style:margin-top="5px"><div class="bar-fill" style:width={s.pct + '%'}></div></div>
        </div>
        <span class="li-side">{s.pct}%</span>
      </div>
    {:else}
      {#if d.ok}<div class="muted">no active streams</div>{/if}
    {/each}
  {/snippet}
</Card>
