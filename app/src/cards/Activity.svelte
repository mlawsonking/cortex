<script>
  import Card from './Card.svelte';
  import { since } from '../lib/fmt.js';

  let { contract, now } = $props();

  const LABEL = { grabbed: 'grabbed', imported: 'imported', failed: 'FAILED', watched: 'watched', other: '' };

  // Collapse consecutive identical events into one row with a count. The *arr history genuinely repeats a grab
  // when it retries, and six identical "Silo S01 ... grabbed" lines pushed everything else off the card. "x6" is
  // strictly more informative than six rows - a retry storm becomes visible instead of just noisy. Nothing is
  // hidden: the count is shown and only ADJACENT identical events merge.
  const rows = $derived.by(() => {
    const out = [];
    for (const e of contract.data?.items ?? []) {
      const prev = out[out.length - 1];
      if (prev && prev.title === e.title && prev.kind === e.kind && prev.detail === e.detail) {
        prev.n += 1;
        prev.ts = Math.max(prev.ts, e.ts);
      } else {
        out.push({ ...e, n: 1 });
      }
    }
    return out;
  });
</script>

<Card title="Activity" {contract} {now} span={true}>
  {#snippet body(d)}
    {#each rows as e, i (e.ts + e.title + i)}
      <div class="li">
        <span class="li-when">{since(e.ts, now)}</span>
        <!-- the count lives OUTSIDE li-main: that element truncates with an ellipsis, so on a phone a long
             release title swallowed the "x10" - hiding the retry storm the count exists to reveal. -->
        <span class="li-main">{e.title}</span>
        {#if e.n > 1}<span class="li-side">&times;{e.n}</span>{/if}
        <span class="li-side k-{e.kind}">{LABEL[e.kind] ?? e.kind}{e.kind === 'watched' && e.detail ? ' · ' + e.detail.replace(/^watched · /, '') : ''}</span>
      </div>
    {:else}
      <div class="muted">no recent activity</div>
    {/each}
  {/snippet}
</Card>
