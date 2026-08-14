<script>
  // I6 Gap Radar - "N films from completing X", for auteurs and for franchises.
  //
  // READ-ONLY BY CONSTRUCTION (v1): no grab / monitor button. The gaps here are real Radarr ids, so a button
  // would be easy - and that is exactly why it is not here. A new write verb needs its own security review and
  // Michael's approval before any card may offer it, and "add 5 films" is a disk-spending action.
  //
  // NO RE-FILTERING HERE. The 1987 year floor, the unreleased-film exclusion and the id verification all live in
  // gap_radar.py, so owned/total is already the whole truth for the set being scored. A card that re-filtered
  // could quietly disagree with the taste model; this one only renders what it was handed.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  // The headline is the single closest thing to done - the whole point of the card in one sentence.
  const lead = $derived.by(() => {
    const rows = [...(contract.data?.auteurs ?? []), ...(contract.data?.franchises ?? [])]
      .filter((r) => r.total > r.owned);
    if (!rows.length) return null;
    rows.sort((a, b) => b.pct - a.pct || a.total - a.owned - (b.total - b.owned));
    const r = rows[0];
    return { name: r.name, gap: r.total - r.owned };
  });

  function gapText(r) {
    const gap = r.total - r.owned;
    if (!gap) return 'complete';
    const names = r.missing.map((m) => `${m.title} (${m.year})`).join(', ');
    const more = gap > r.missing.length ? `, +${gap - r.missing.length} more` : '';
    return `${gap} to go: ${names}${more}`;
  }
</script>

<Card title="Gap radar" {contract} {now} span={true}>
  {#snippet body(d)}
    {#if lead}
      <div class="stats" style:margin-bottom="10px">
        <div class="stat accent">
          <div class="n">{lead.gap}</div>
          <div class="l">film{lead.gap === 1 ? '' : 's'} from completing {lead.name}</div>
        </div>
        <div class="stat"><div class="n">{d.auteurs.length}</div><div class="l">auteurs tracked</div></div>
        <div class="stat">
          <div class="n">{d.totals.franchises_incomplete}</div>
          <div class="l">franchises unfinished</div>
        </div>
      </div>
    {/if}

    <div class="muted" style:margin-bottom="6px">
      Auteurs &mdash; canonical filmography owned, closest to complete first:
    </div>
    {#each d.auteurs as a (a.name)}
      <div class="bar-row">
        <div class="bar-label">{a.name}</div>
        <div class="bar"><div class="bar-fill" style:width={a.pct + '%'}></div></div>
        <div class="bar-pct">{a.owned}/{a.total}</div>
      </div>
      <div class="muted gap" class:done={a.owned >= a.total}>
        {gapText(a)}{#if a.unresolved}
          <span class="k-failed"> &middot; {a.unresolved} curated title{a.unresolved === 1 ? '' : 's'} unmatched, not scored</span>
        {/if}
      </div>
    {:else}
      <div class="muted">no auteur could be resolved this run</div>
    {/each}

    <div class="muted" style:margin="12px 0 6px">
      Franchises &mdash; collections the shelf already owns 2+ of, ranked by how close they are:
    </div>
    {#each d.franchises as f (f.tmdb)}
      <div class="li">
        <span class="li-main">
          {f.name}
          <span class="muted">&mdash; {gapText(f)}</span>
        </span>
        <span class="li-side">{f.owned}/{f.total}</span>
      </div>
    {:else}
      <div class="muted">no franchise with 2+ owned films is incomplete</div>
    {/each}

    <div class="muted" style:margin-top="10px">
      Films released before {d.year_floor} are never counted as gaps &mdash; the year floor is a standing taste
      rule, applied in the producer, so every total above is already floor-adjusted. &ldquo;Owned&rdquo; means a
      file on disk; a film already parked in Radarr still shows as a gap until it lands.
      Read-only: a &ldquo;grab the rest&rdquo; verb spends disk, so it needs its own security review before any
      button appears here.
    </div>
    <div class="muted" style:margin-top="6px">{d.generated_note}</div>
  {/snippet}
</Card>

<style>
  /* the gap line belongs to the bar above it, so it hangs tight under the row */
  .gap { margin: -5px 0 9px 0; }
  .gap.done { opacity: 0.55; }
</style>
