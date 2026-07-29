<script>
  // Tonight's Pick. The reroll button calls the EXISTING /act/reroll verb, which only re-pins an index in a local
  // JSON file and regenerates - it triggers zero Radarr/qBit activity and downloads nothing. Backdrop art is
  // served from a producer-side same-origin cache (/art/<tmdb>.jpg); the app never fetches TMDB itself, so the
  // page makes no external requests and the strict CSP holds.
  import { freshness, humanAge } from '../lib/contracts.svelte.js';
  import { act } from '../lib/act.js';

  let { contract, now } = $props();

  let busy = $state(false);
  let msg = $state('');
  let msgErr = $state(false);

  const fresh = $derived(contract.meta ? freshness(contract.meta, now) : null);

  async function reroll() {
    // The button label carries the progress state; msg is reserved for outcomes worth words (i.e. failures).
    busy = true; msg = ''; msgErr = false;
    try {
      await act('reroll');
      await contract.refresh();
    } catch (e) {
      msg = String(e?.message ?? e); msgErr = true;
    } finally {
      busy = false;
    }
  }
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
      <div class="hero-title">{p.title} <span class="hero-year">{p.year ?? ''}</span></div>
      <div class="hero-why">
        {#if p.why}because you loved <strong>{p.why}</strong>{:else}tuned to your taste{/if}
        {#if p.genres}<span class="muted"> · {p.genres}</span>{/if}
      </div>
      <div class="hero-actions">
        <button class="btn" disabled={busy} onclick={reroll}>{busy ? 'rerolling...' : 'reroll'}</button>
        <span class="muted">pick {contract.data.idx % Math.max(1, contract.data.pool) + 1} of {contract.data.pool}</span>
        {#if msg}<span class="act-msg" class:err={msgErr}>{msg}</span>{/if}
      </div>
    {/if}
  </div>
</section>
