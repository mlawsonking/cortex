<script>
  import Card from './Card.svelte';
  import { count, speed } from '../lib/fmt.js';

  let { contract, now } = $props();
</script>

<Card title="Download pipeline" {contract} {now}>
  {#snippet body(d)}
    <div class="stats">
      <div class="stat"><div class="n">{count(d.downloading)}</div><div class="l">Downloading</div></div>
      <div class="stat"><div class="n">{count(d.seeding)}</div><div class="l">Seeding</div></div>
      <div class="stat"><div class="n">{d.ratio === null ? '-' : d.ratio.toFixed(2)}</div><div class="l">Ratio</div></div>
    </div>

    <div class="muted" style:margin-top="10px">
      &darr; {speed(d.dl_bps)} &middot; &uarr; {speed(d.ul_bps)}
      &middot; queue: Radarr {count(d.queue.radarr)} / Sonarr {count(d.queue.sonarr)}
      {#if d.torrents !== null}&middot; {d.torrents} torrents{/if}
    </div>

    <div style:margin-top="10px">
      {#each d.active as t (t.name)}
        <div class="li">
          <span class="li-main">{t.name}</span>
          <span class="li-side">{t.pct.toFixed(0)}% &middot; {t.mbps.toFixed(1)} MB/s</span>
        </div>
      {:else}
        <div class="muted">nothing actively downloading</div>
      {/each}
    </div>
  {/snippet}
</Card>
