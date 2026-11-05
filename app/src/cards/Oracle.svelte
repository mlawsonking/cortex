<script>
  // Oracle: the nightly deterministic health score + brief, and the HEVC reclaim list.
  // The reclaim list is PROPOSAL-ONLY by design - there is no re-encode verb on the server, so this card cannot
  // offer one. It reports what x264 titles are costing; acting on it stays a deliberate human step.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  function scoreClass(s) {
    if (s === null || s === undefined) return 'unk';
    if (s >= 85) return 'ok';
    if (s >= 60) return 'warn';
    return 'bad';
  }
</script>

<Card title="Oracle" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="row" style:margin-bottom="10px">
      <span class="dot {scoreClass(d.score)}"></span>
      <strong class="figure" style:color="var(--text-strong)">
        {d.score === null ? '-' : d.score}<span class="muted">/100</span>
      </strong>
      <span class="muted">{d.why}</span>
    </div>

    {#each d.brief as line, i (i)}
      <div class="li"><span class="li-main">{line}</span></div>
    {/each}

    {#if d.codec.length}
      <div class="muted" style:margin-top="10px">
        Reclaimable by re-encoding to HEVC (proposal only &mdash; nothing here re-encodes):
      </div>
      {#each d.codec as c (c.title)}
        <div class="li">
          <span class="li-main">{c.title}</span>
          <span class="li-side">{c.gb.toFixed(1)} GB</span>
        </div>
      {/each}
    {/if}
  {/snippet}
</Card>
