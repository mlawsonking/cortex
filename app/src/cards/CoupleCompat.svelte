<script>
  // I5 Couple Compatibility - the overlap between his learned taste and her rule-defined lanes, over films the
  // server ALREADY OWNS and nobody has watched. Verb 'date-night-refresh' (M3-approved 2026-08-14): rebuilds
  // the Plex "Date Night" collection from this shelf - tag edits on owned items only, replace semantics,
  // verify-by-requery server-side. Nothing downloads, nothing deletes.
  //
  // THE ASYMMETRY IS SHOWN, NOT HIDDEN: his side comes from play history, her side from brain\her-lanes.json,
  // because the household shares one Plex account and she has no separate signal to learn from. The footer says
  // so, so nobody reads this card as "the server figured out what she likes".
  import Card from './Card.svelte';
  import ActionBtn from './ActionBtn.svelte';

  let { contract, now } = $props();

  const laneLabel = $derived.by(() => {
    const map = {};
    for (const l of contract.data?.lanes ?? []) map[l.key] = l.label;
    return map;
  });

  // his_score is a mean of 0..1 genre weights: a bar is honest here, a percentage would over-claim precision.
  function bar(s) {
    return Math.round(Math.max(0, Math.min(1, s)) * 100);
  }
</script>

<Card title="Couple compatibility" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="stats" style:margin-bottom="10px">
      <div class="stat accent"><div class="n">{d.date_night.length}</div><div class="l">date-night picks</div></div>
      <div class="stat"><div class="n">{d.matched_any}</div><div class="l">on a shelf</div></div>
      <div class="stat"><div class="n">{d.pool_total}</div><div class="l">unwatched pool</div></div>
    </div>

    <div class="muted" style:margin-bottom="6px" style:display="flex" style:align-items="center" style:gap="8px">
      <span>Date night &mdash; already on the shelf, fits her lanes, ranked by his taste:</span>
      <ActionBtn label="refresh Date Night in Plex" verb="date-night-refresh" busyLabel="tagging..."
                 title="Rebuilds the Plex 'Date Night' collection from this shelf. Tag edits only - nothing downloads or deletes." />
    </div>
    {#each d.date_night as p, i (p.ratingKey ?? p.tmdb ?? i)}
      <div class="li">
        <span class="li-main">
          {p.title} <span class="muted">{p.year ?? ''}</span>
          {#each p.lanes as k (k)}<span class="lane">{laneLabel[k] ?? k}</span>{/each}
        </span>
        <span class="li-side">
          <span class="mini"><span class="mini-fill" style:width={bar(p.his_score) + '%'}></span></span>
          {p.his_score.toFixed(2)}
        </span>
      </div>
    {:else}
      <div class="muted">nothing in the unwatched pool fits both sides right now</div>
    {/each}

    <div class="muted" style:margin="12px 0 6px">Her lanes, and what the shelf holds for each:</div>
    {#each d.lanes as l (l.key)}
      <div class="li">
        <span class="li-main">
          <span class="lane">{l.label}</span>
          {#if l.top.length}
            {l.top.slice(0, 3).map((t) => t.title).join(' · ')}
          {:else}
            <span class="k-failed">no match in the pool</span>
          {/if}
        </span>
        <span class="li-side">{l.matches} film{l.matches === 1 ? '' : 's'}</span>
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      his taste = {d.taste_source === 'taste-graph'
        ? 'genre weights learned from his own play history'
        : 'genre means derived from his Trakt ratings (taste-graph had nothing usable)'};
      her lanes are hand-written rules in brain\her-lanes.json, not a learned persona &mdash; she shares the
      household Plex account, so there is no separate history to learn from. {d.pool_total - d.matched_any}
      unwatched films match no lane and are deliberately off these shelves.
      "Refresh" rebuilds the Plex "Date Night" collection to match this shelf exactly (replace semantics).
    </div>
  {/snippet}
</Card>

<style>
  .lane {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    padding: 1px 6px;
    margin-left: 6px;
    border-radius: 999px;
    color: var(--accent);
    background: rgba(188, 140, 255, 0.12);
    border: 1px solid rgba(188, 140, 255, 0.32);
    vertical-align: 1px;
  }
  /* a 0..1 mean deserves a bar, not a fake percentage */
  .mini {
    display: inline-block;
    width: 46px;
    height: 5px;
    margin-right: 6px;
    border-radius: 999px;
    background: var(--bg-sunken);
    border: 1px solid var(--line-soft);
    overflow: hidden;
    vertical-align: middle;
  }
  .mini-fill { display: block; height: 100%; background: var(--accent); }
</style>
