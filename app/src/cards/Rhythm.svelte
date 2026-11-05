<script>
  // I1 Rhythm Map - when this household ACTUALLY watches. Heat grid of plays by weekday x hour, switchable
  // between the whole household and the top users. Read-only; its future job is feeding the schedule-aware
  // Tonight's Pick (auto Date-Night pick in the Friday-evening slot).
  import Card from './Card.svelte';

  let { contract, now } = $props();

  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  let who = $state('all');

  const view = $derived.by(() => {
    const d = contract.data;
    if (!d) return null;
    if (who === 'all') return { label: 'household', matrix: d.all, plays: d.total_plays };
    const u = d.users.find((x) => x.user === who);
    return u ? { label: u.user, matrix: u.matrix, plays: u.plays } : { label: 'household', matrix: d.all, plays: d.total_plays };
  });

  const maxCell = $derived.by(() => {
    let m = 1;
    for (const row of view?.matrix ?? []) for (const c of row) if (c > m) m = c;
    return m;
  });

  function heat(c) {
    if (!c) return 'transparent';
    const a = 0.15 + 0.85 * (c / maxCell);
    return `rgba(88, 166, 255, ${a.toFixed(2)})`;
  }

  function slotLabel(s) {
    const h = s.hour;
    const t = h === 0 ? '12am' : h < 12 ? h + 'am' : h === 12 ? '12pm' : (h - 12) + 'pm';
    return `${DAYS[s.weekday]} ${t}`;
  }
</script>

<Card title="Rhythm map" {contract} {now} span={true}>
  {#snippet body(d)}
    <div class="row" style:margin-bottom="10px" style:flex-wrap="wrap">
      <button class="btn ghost" class:sel={who === 'all'} onclick={() => (who = 'all')}>household</button>
      {#each d.users as u (u.user)}
        <button class="btn ghost" class:sel={who === u.user} onclick={() => (who = u.user)}>{u.user}</button>
      {/each}
    </div>

    <div class="heat-wrap">
    <div class="heat">
      <div class="heat-corner"></div>
      {#each [0, 3, 6, 9, 12, 15, 18, 21] as h (h)}
        <div class="heat-hour" style:grid-column={h + 2}>{h === 0 ? '12a' : h < 12 ? h + 'a' : h === 12 ? '12p' : (h - 12) + 'p'}</div>
      {/each}
      {#each view.matrix as row, di (di)}
        <div class="heat-day" style:grid-row={di + 2}>{DAYS[di]}</div>
        {#each row as c, hi (hi)}
          <div class="heat-cell" style:grid-row={di + 2} style:grid-column={hi + 2}
               style:background={heat(c)} title={DAYS[di] + ' ' + hi + ':00 - ' + c + ' plays'}></div>
        {/each}
      {/each}
    </div>
    </div>

    <div class="muted" style:margin-top="10px">
      {#if d.top_slots.length}
        prime slots: {d.top_slots.slice(0, 3).map((s) => slotLabel(s) + ' ×' + s.plays).join(' · ')} &nbsp;&middot;&nbsp;
      {/if}
      {view.plays} plays ({d.movies} movies / {d.episodes} episodes) over {d.window_days} days
      {#if view.plays < 60}&mdash; thin sample, treat as a hint rather than a habit{/if}
    </div>
  {/snippet}
</Card>

<style>
  .heat {
    display: grid;
    grid-template-columns: 34px repeat(24, 1fr);
    grid-template-rows: 16px repeat(7, 18px);
    gap: 2px;
    min-width: 480px;
  }
  .heat-corner { grid-row: 1; grid-column: 1; }
  .heat-hour { grid-row: 1; font-size: var(--fs-xs); color: var(--text-faint); }
  .heat-day { grid-column: 1; font-size: var(--fs-xs); color: var(--text-dim); align-self: center; }
  .heat-cell { border-radius: 3px; background: var(--bg-sunken); border: 1px solid var(--line-soft); }
  .btn.sel { border-color: var(--info); color: var(--info); }
  /* wide content scrolls inside its own box - the page body must never scroll horizontally */
  .heat-wrap { overflow-x: auto; padding-bottom: 4px; }
</style>
