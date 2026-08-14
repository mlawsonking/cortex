<script>
  // I10 Cost of Quality. READ-ONLY by construction: this card informs a policy decision (which profile is worth
  // its disk) and offers no verb - there is nothing here to click, and nothing here should ever become clickable
  // without its own security review.
  //
  // The projection line is deliberately allowed to say NOTHING. slope_gb_per_week is null whenever no series
  // supports a slope, and the card then prints the producer's honest note instead of a comforting number. This
  // card exists to replace a forecast that was seen swinging 16 -> 8 months within an hour.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  function tb(gb) {
    return gb >= 1000 ? (gb / 1000).toFixed(1) + ' TB' : Math.round(gb) + ' GB';
  }
</script>

<Card title="Cost of quality" {contract} {now} span={true}>
  {#snippet body(d)}
    {@const maxGb = Math.max(...d.profiles.map((p) => p.total_gb), 1)}

    <div class="stats" style:margin-bottom="12px">
      <div class="stat accent"><div class="n">{tb(d.movies_total_gb)}</div><div class="l">movies on disk</div></div>
      <div class="stat"><div class="n">{tb(d.g_free_gb)}</div><div class="l">G: free of {tb(d.g_total_gb)}</div></div>
      <div class="stat">
        <div class="n" class:dim={d.slope_gb_per_week === null}>
          {d.slope_gb_per_week === null ? '-' : Math.round(d.slope_gb_per_week) + ' GB'}
        </div>
        <div class="l">growth per week</div>
      </div>
      <div class="stat">
        <div class="n" class:dim={d.full_in_years === null}>
          {d.full_in_years === null ? '-' : d.full_in_years.toFixed(1) + ' yr'}
        </div>
        <div class="l">until G: is full</div>
      </div>
    </div>

    {#each d.profiles as p (p.profile)}
      <div class="bar-row" style:margin-bottom="4px">
        <div class="bar-label">{p.profile} <span class="muted">{p.films} films</span></div>
        <div class="bar"><div class="bar-fill" style:width={(100 * p.total_gb) / maxGb + '%'}></div></div>
        <div class="bar-pct">{tb(p.total_gb)}</div>
      </div>
      <div class="muted" style:margin="0 0 9px 0">
        {p.avg_gb.toFixed(1)} GB per film on average
        {#if p.biggest.length}
          &middot; biggest: {#each p.biggest as b, i}{i ? ', ' : ''}{b.title} ({b.gb.toFixed(1)} GB){/each}
        {/if}
      </div>
    {/each}

    <div class="row" style:margin-top="10px">
      {#if d.slope_gb_per_week === null}
        <span>No slope available &mdash; the projection cannot be computed from what exists.</span>
      {:else}
        <span>G: is filling at <strong>{Math.round(d.slope_gb_per_week)} GB/week</strong>
          {#if d.full_in_years !== null}&mdash; full in <strong>~{d.full_in_years.toFixed(1)} years</strong>{/if}
        </span>
      {/if}
    </div>
    <div class="muted" style:margin-top="4px">{d.note}</div>
    <div class="muted" style:margin-top="4px">projection source: {d.forecast_source}</div>
  {/snippet}
</Card>
