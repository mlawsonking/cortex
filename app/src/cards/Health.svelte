<script>
  // Protection & Health. One deliberate improvement over the legacy board: a probe that reports 'n/a' could NOT
  // RUN, and the old page painted those green alongside genuine passes. An unrunnable probe is not a healthy
  // probe - it renders as unknown here, because "we didn't check" and "we checked and it's fine" are different
  // facts and only one of them should be reassuring.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  const unknown = (p) => String(p.detail).trim().toLowerCase() === 'n/a';
</script>

<Card title="Protection &amp; Health" {contract} {now}>
  {#snippet body(d)}
    {@const failing = d.probes.filter((p) => !p.ok && !unknown(p)).length}
    {@const unchecked = d.probes.filter(unknown).length}

    {#each d.probes as p (p.name)}
      <div class="li">
        <span class="dot" class:ok={p.ok && !unknown(p)} class:bad={!p.ok && !unknown(p)} class:unk={unknown(p)}></span>
        <span class="li-main">{p.name}</span>
        <span class="li-side">{unknown(p) ? 'not checked' : p.detail}</span>
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      {#if d.incidents_7d.length}
        7d flaps: {d.incidents_7d.map((i) => i.service + ' x' + i.downs).join(' · ')}
      {:else}
        no service flaps in 7 days
      {/if}
      {#if unchecked}<br />{unchecked} probe{unchecked > 1 ? 's' : ''} could not run &mdash; shown as unknown, not as passing{/if}
      {#if failing}<br /><span class="k-failed">{failing} probe{failing > 1 ? 's' : ''} failing</span>{/if}
    </div>
  {/snippet}
</Card>
