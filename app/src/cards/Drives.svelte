<script>
  // SMART drives. The verdict comes from the producer, NOT from this card - which matters, because the house
  // rule is that reallocated sectors which are stable are not a failing drive (d3 / 000D1RAN has sat at 448
  // realloc, 0 pending for ~2 years and is explicitly NOT to be flagged). Growth detection belongs to
  // smart-check-weekly.ps1; a dashboard card that re-derived "failing" from raw counters is precisely how the
  // false "drive increasingly failing" alert happened on 2026-07-26.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  const VERDICT = { PASS: 'ok', WARN: 'unk', RMA: 'bad', FAIL: 'bad' };

  function tempClass(t) {
    if (!Number.isFinite(t)) return '';
    if (t >= 55) return 'k-failed';
    if (t >= 48) return 'k-grabbed';
    return '';
  }
</script>

<Card title="Drives · SMART" {contract} {now}>
  {#snippet body(d)}
    {@const watched = d.drives.filter((x) => x.verdict !== 'PASS').length}
    <div class="stats" style:margin-bottom="10px">
      <div class="stat"><div class="n">{d.drives.length}</div><div class="l">Drives</div></div>
      <div class="stat"><div class="n" class:dim={watched === 0}>{watched}</div><div class="l">Watched</div></div>
    </div>

    {#each d.drives as k (k.dev + k.serial)}
      <div class="li">
        <span class="dot {VERDICT[k.verdict] ?? 'unk'}"></span>
        <span class="li-main">{k.model} <span class="muted">{k.serial}</span></span>
        <span class="li-side {tempClass(k.temp)}">{k.temp === null ? '-' : k.temp + '°C'}</span>
        <span class="li-side">{k.verdict}</span>
      </div>
    {/each}

    {#if watched > 0}
      <div class="muted" style:margin-top="8px">
        WARN = non-zero reallocated sectors that are <em>stable</em>. Growth, not presence, is what matters &mdash;
        that judgement is the weekly SMART check's, not this card's.
      </div>
    {/if}
  {/snippet}
</Card>
