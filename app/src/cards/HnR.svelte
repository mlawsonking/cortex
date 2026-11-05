<script>
  // H&R Sentinel. STRUCTURALLY READ-ONLY and it must stay that way: on Michael's private trackers ANY downloaded
  // data - complete or partial, seeding or stalled - is a hit-and-run liability. The only sanctioned removal test
  // is downloaded == 0 bytes, and that decision lives server-side. There is deliberately no verb on this card,
  // and none may ever be added: the app is not permitted to be one click away from a tracker ban.
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="H&amp;R Sentinel" {contract} {now}>
  {#snippet body(d)}
    <div class="row" style:margin-bottom="10px">
      <strong class="figure" style:color={d.count ? 'var(--warn)' : 'var(--ok)'}>{d.count}</strong>
      <span class="muted">seeding below a 1.0 ratio</span>
    </div>

    {#each d.torrents as t (t.name)}
      <div class="bar-row">
        <div class="bar-label">{t.name}</div>
        <div class="bar">
          <div class="bar-fill {t.ratio < 0.5 ? 'crit' : 'warn'}" style:width={Math.min(100, t.ratio * 100) + '%'}></div>
        </div>
        <div class="bar-pct">{t.ratio.toFixed(2)}</div>
      </div>
    {:else}
      <div class="muted">every seeding torrent is at or above 1.0</div>
    {/each}

    <div class="muted" style:margin-top="8px">
      Read-only by design &mdash; seed to 1.0, never remove mid-seed. Partial data counts as H&amp;R too.
    </div>
  {/snippet}
</Card>
