<script>
  // Tonight's Pick. The reroll button calls the EXISTING /act/reroll verb, which only re-pins an index in a local
  // JSON file and regenerates - it triggers zero Radarr/qBit activity and downloads nothing. Backdrop art is
  // served from a producer-side same-origin cache (/art/<tmdb>.jpg); the app never fetches TMDB itself, so the
  // page makes no external requests and the strict CSP holds.
  import { freshness, humanAge } from '../lib/contracts.svelte.js';
  import ActionBtn from './ActionBtn.svelte';
  import WatchBtn from './WatchBtn.svelte';
  import ThumbBtns from './ThumbBtns.svelte';
  import { ledger } from '../lib/taste.svelte.js';
  $effect(() => ledger.start());

  let { contract, now } = $props();

  const fresh = $derived(contract.meta ? freshness(contract.meta, now) : null);
</script>

<section class="hero">
  {#if contract.data?.pick?.art_local}
    <div class="hero-art" style:background-image={'url(' + contract.data.pick.art_local + ')'}></div>
    <div class="hero-scrim"></div>
  {/if}

  <div class="hero-body">
    <div class="card-head">
      <div class="hero-label">Tonight's Pick</div>
      <span
        class="badge {contract.error && !contract.env ? 'error' : (fresh?.state ?? 'fresh')}"
        title={contract.meta ? contract.meta.contract + ' v' + contract.meta.version + '\nproduced ' + contract.meta.generated_at : ''}
      >
        {#if contract.error && !contract.env}unavailable
        {:else if fresh?.state === 'stale'}stale · {humanAge(fresh.ageSeconds)}
        {:else if fresh}{humanAge(fresh.ageSeconds)}{/if}
      </span>
    </div>

    {#if contract.loading && !contract.env}
      <div class="skeleton" style:width="55%" style:height="24px"></div>
    {:else if contract.error && !contract.env}
      <div class="state err">could not load the pick</div>
      <div class="state-detail">{contract.name}: {contract.error}</div>
    {:else if !contract.data?.pick}
      <div class="hero-title">No pick available</div>
      <div class="hero-why">
        The recommendation pool is empty ({contract.data?.pool ?? 0} candidates). Refresh the recommender rather
        than trusting a stale suggestion.
      </div>
    {:else}
      {@const p = contract.data.pick}
      <div class="hero-title">
        {p.title} <span class="hero-year">{p.year ?? ''}</span>
        {#if p.mode === 'date-night'}<span class="dn-chip">Friday date night</span>{/if}
      </div>
      <div class="hero-why">
        {#if p.mode === 'date-night'}owned &amp; unwatched, fits her lanes, ranked by your taste
          {#if p.genres}<span class="muted"> · {p.genres}</span>{/if}
        {:else}
          {#if p.mode === 'missed-gems'}<span class="shelf">on your shelf, never played</span> &middot; {/if}
          {#if p.why}because you loved <strong>{p.why}</strong>{:else}tuned to your taste{/if}
          {#if p.genres}<span class="muted"> · {p.genres}</span>{/if}
        {/if}
      </div>
      <div class="hero-actions">
        <ActionBtn label="reroll" verb="reroll" busyLabel="rerolling..." done={() => contract.refresh()}
                   title="Re-pins a local index and regenerates. Triggers no download." />
        {#if p.rating_key}<WatchBtn ratingKey={p.rating_key} title={p.title} />{/if}
        {#if p.tmdb && p.mode !== 'date-night'}<ThumbBtns tkey={'movie:' + p.tmdb} title={p.title} />{/if}
        <span class="muted">pick {contract.data.idx % Math.max(1, contract.data.pool) + 1} of {contract.data.pool}</span>
      </div>
    {/if}
  </div>
</section>

<style>
  .shelf { color: var(--ok); }
  .dn-chip {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    padding: 2px 8px;
    margin-left: 8px;
    border-radius: 999px;
    color: var(--accent);
    background: rgba(188, 140, 255, 0.14);
    border: 1px solid rgba(188, 140, 255, 0.35);
    vertical-align: middle;
  }
</style>
