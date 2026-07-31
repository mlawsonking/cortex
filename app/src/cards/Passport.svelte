<script>
  // Auteur passport: filmography completion per director, and a one-click grab for a specific gap.
  // The 1987 year-floor and every other taste rule live in the producer (passport.ps1), never here - a card must
  // not be able to quietly disagree with the taste model by re-filtering.
  // No grab button here on purpose: the /act/grab verb takes a Radarr id, and this contract carries only the
  // missing TITLES. Rendering a button that guesses at an id would be a way to grab the wrong film - so the card
  // reports the gaps and the grab stays where an id actually exists.
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="Auteur passport" {contract} {now} span={true}>
  {#snippet body(d)}
    {#each d.directors.slice(0, 16) as dir (dir.name)}
      {@const pctOwned = dir.total ? Math.round((100 * dir.own) / dir.total) : 0}
      <div class="bar-row">
        <div class="bar-label">{dir.name}</div>
        <div class="bar"><div class="bar-fill" style:width={pctOwned + '%'}></div></div>
        <div class="bar-pct">{dir.own}/{dir.total}</div>
      </div>
      {#if dir.missing?.length}
        <div class="muted" style:margin="-4px 0 9px 0">
          missing: {dir.missing.slice(0, 4).join(' · ')}{dir.missing.length > 4 ? ' · +' + (dir.missing.length - 4) : ''}
        </div>
      {/if}
    {/each}
    <div class="muted" style:margin-top="6px">owned / total per director &mdash; parked films are one grab away</div>
  {/snippet}
</Card>
