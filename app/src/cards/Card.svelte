<script>
  // The card shell. Every card in this app goes through here, which is how the honesty rules become structural
  // rather than a thing each card has to remember:
  //   * the freshness badge comes from the contract's own _meta, so a card cannot show data it could not date;
  //   * a load/parse failure renders an error state - never a plausible-looking empty card;
  //   * if a refresh starts failing while we still hold a good envelope, we keep showing the good data AND say
  //     that refreshes are failing. Silently serving last-known-good as if it were live is the exact bug class
  //     (stale parity widget, false drive alert) this rebuild exists to kill.
  import { freshness, humanAge } from '../lib/contracts.svelte.js';

  let { title, contract, now, span = false, body } = $props();

  const fresh = $derived(contract.meta ? freshness(contract.meta, now) : null);
  const badgeClass = $derived(contract.error && !contract.env ? 'error' : (fresh?.state ?? 'fresh'));
  const badgeText = $derived.by(() => {
    if (contract.error && !contract.env) return 'unavailable';
    if (!fresh) return '';
    const age = humanAge(fresh.ageSeconds);
    if (fresh.state === 'stale') return 'stale · ' + age;
    if (fresh.state === 'snapshot') return 'snapshot · ' + age;
    if (fresh.state === 'error') return 'undated';
    return age;
  });
  const detail = $derived.by(() => {
    const m = contract.meta;
    if (!m) return '';
    const slo = m.slo_seconds === null || m.slo_seconds === undefined
      ? 'no schedule exists for this producer, so freshness is never claimed'
      : 'SLO ' + Math.round(m.slo_seconds / 60) + 'm';
    return `${m.contract} v${m.version}\nproduced ${m.generated_at}\nby ${m.producer}\n${slo}`;
  });
</script>

<section class="card" class:span-all={span}>
  <div class="card-head">
    <h2 class="card-title">{title}</h2>
    <span class="badge {badgeClass}" title={detail}>{badgeText}</span>
  </div>

  {#if contract.loading && !contract.env}
    <div class="skeleton"></div>
    <div class="state">loading contract&hellip;</div>
  {:else if contract.error && !contract.env}
    <div class="state err">could not load this card's data</div>
    <div class="state-detail">{contract.name}: {contract.error}</div>
  {:else if contract.data === null || contract.data === undefined}
    <div class="state err">contract carried no data</div>
  {:else}
    {@render body(contract.data)}
    {#if contract.error}
      <div class="state-detail" style:margin-top="10px">refresh failing ({contract.error}) &mdash; the values above are the last good read</div>
    {/if}
  {/if}
</section>
