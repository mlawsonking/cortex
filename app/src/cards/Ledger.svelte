<script>
  // I2 Compression Ledger. Numbers only, deliberately: the "re-grab compact" verb does not exist server-side,
  // and a new verb needs its own security review + Michael's approval before any card may offer it.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  function tb(gb) {
    return gb >= 1000 ? (gb / 1000).toFixed(1) + ' TB' : Math.round(gb) + ' GB';
  }
</script>

<Card title="Compression ledger" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="stats" style:margin-bottom="10px">
      <div class="stat accent"><div class="n">{tb(d.saved_gb)}</div><div class="l">saved by x265</div></div>
      <div class="stat"><div class="n">{d.hevc.count}</div><div class="l">HEVC files ({tb(d.hevc.gb)})</div></div>
      <div class="stat"><div class="n">{d.avc.count}</div><div class="l">x264 files ({tb(d.avc.gb)})</div></div>
      <div class="stat"><div class="n">{tb(d.reclaim_potential_gb)}</div><div class="l">reclaimable</div></div>
    </div>

    <div class="muted" style:margin-bottom="6px">
      Top reclaim candidates &mdash; big x264 files weighted by low rewatch odds (unwatched &gt; mediocre &gt; loved):
    </div>
    {#each d.reclaim.slice(0, 10) as r (r.radarrId)}
      <div class="li">
        <span class="li-main">{r.title} <span class="muted">{r.year ?? ''}</span></span>
        <span class="li-side">{r.gb.toFixed(1)} GB &rarr; save {r.save_gb.toFixed(1)}
          &middot; {r.rating != null ? 'rated ' + r.rating : r.watched ? 'watched' : 'unwatched'}</span>
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      showing 10 of {d.reclaim_candidates} candidates &middot; savings estimated at x265 &asymp; {Math.round(d.hevc_factor * 100)}% of x264 size
      &middot; proposal-only: a re-grab verb needs its own security review before buttons appear here
    </div>
  {/snippet}
</Card>
