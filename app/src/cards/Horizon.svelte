<script>
  // I4 H&R Horizon - projected ratio-1.0 dates per tracker from measured upload velocity. Read-only forever,
  // like the sentinel: visibility, not verbs. "never at current rate" is an honest label for a velocity too
  // low to project - especially common while historic averages still reflect the dead-inbound era.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  function days(d) {
    if (d === null || d === undefined) return 'never @ rate';
    if (d < 1) return '<1d';
    if (d <= 60) return Math.round(d) + 'd';
    return Math.round(d / 30) + 'mo';
  }
</script>

<Card title="H&amp;R horizon" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="stats" style:margin-bottom="10px">
      <div class="stat"><div class="n">{d.totals.below_goal}</div><div class="l">below 1.0 goal</div></div>
      <div class="stat"><div class="n">{(d.totals.remaining_gb / 1000).toFixed(1)} TB</div><div class="l">upload remaining</div></div>
      <div class="stat"><div class="n" class:dim={!d.totals.never_at_current_rate}>{d.totals.never_at_current_rate}</div><div class="l">never @ current rate</div></div>
    </div>

    {#each d.trackers.slice(0, 6) as t (t.tracker)}
      <div class="li">
        <span class="li-main">{t.tracker}</span>
        <span class="li-side">
          {t.below_goal} below &middot; {t.remaining_gb.toFixed(0)} GB left
          &middot; ≤7d: {t.on_track_week} &middot; ≤30d: {t.on_track_month}
          &middot; <span class={t.never_at_current_rate ? 'k-failed' : ''}>{t.never_at_current_rate} stalled</span>
        </span>
      </div>
    {/each}

    <div class="muted" style:margin="8px 0 4px">highest-risk (slowest, most remaining):</div>
    {#each d.risk_feed.slice(0, 6) as r, i (r.name + i)}
      <div class="li">
        <span class="li-main">{r.name}</span>
        <span class="li-side">{r.tracker.split('.')[0]} &middot; {r.ratio.toFixed(2)} &middot; {r.remaining_gb.toFixed(1)} GB &middot;
          <span class={r.projected_days === null ? 'k-failed' : ''}>{days(r.projected_days)}</span></span>
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      velocities are lifetime averages &mdash; they still carry the no-inbound era; expect projections to improve
      now the forwarded port is live &middot; read-only by design, the exposure self-heal handles silent torrents
    </div>
  {/snippet}
</Card>
