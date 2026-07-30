<script>
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="Security posture" {contract} {now}>
  {#snippet body(d)}
    {#each d.probes as p (p.name)}
      <div class="li">
        <span class="dot" class:ok={p.ok} class:bad={!p.ok}></span>
        <span class="li-main">{p.name}</span>
        <span class="li-side">{p.detail}</span>
      </div>
    {/each}
    <div class="muted" style:margin-top="8px">
      Tailscale-only &middot; /act nonce-guarded &middot; no new exposure.
      A listening-port finding is a diff against a recorded baseline &mdash; a legitimately added service shows here
      until the baseline is re-recorded.
    </div>
  {/snippet}
</Card>
