<script>
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="Recently added to Plex" {contract} {now} span={true}>
  {#snippet body(d)}
    {#if d.recent.length}
      <div class="shelf">
        {#each d.recent as m (m.title + m.thumb)}
          <div class="ptile">
            {#if m.thumb}
              <img class="poster" loading="lazy" alt="" src={'/photo?key=' + encodeURIComponent(m.thumb) + '&width=200'} />
            {:else}
              <div class="poster"></div>
            {/if}
            <div class="pcap" title={m.title}>{m.title}</div>
          </div>
        {/each}
      </div>
    {:else}
      <div class="muted">nothing added recently</div>
    {/if}
  {/snippet}
</Card>
