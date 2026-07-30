<script>
  import Card from './Card.svelte';
  import { dayLabel } from '../lib/fmt.js';

  let { contract, now } = $props();
</script>

<Card title="Release calendar" {contract} {now}>
  {#snippet body(d)}
    {#each d.items as it, i (it.date + it.title + it.detail + i)}
      <div class="li">
        <span class="li-when">{dayLabel(it.date, now)}</span>
        <span class="li-main">{it.title}</span>
        <span class="li-side {it.kind === 'episode' ? 'k-grabbed' : 'k-watched'}">{it.detail}</span>
      </div>
    {:else}
      <div class="muted">nothing in the next {d.days} days</div>
    {/each}

    <div class="muted" style:margin-top="8px">
      {#if d.total > d.items.length}
        showing {d.items.length} of {d.total} in the next {d.days} days
      {:else}
        next {d.days} days
      {/if}
    </div>
  {/snippet}
</Card>
