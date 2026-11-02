<script>
  // The 1-10 tap row (decision D2: his 488 ratings are on a 10-point scale; the star equivalent sits underneath).
  // Pure input: it never talks to the server itself - the parent owns the optimistic state and the undo.
  let { title = '', disabled = false, onpick, compact = false } = $props();   // compact = two rows of five (narrow cards)
  const vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  let hover = $state(0);
</script>

<div class="rr" role="group" aria-label={'Rate ' + title + ' from 1 to 10'}>
  <div class="rr-row" class:compact>
    {#each vals as v (v)}
      <button class="rr-b" class:lo={v <= 4} class:hi={v >= 8} {disabled}
              aria-label={'Rate ' + title + ' ' + v + ' out of 10'}
              onmouseenter={() => (hover = v)} onmouseleave={() => (hover = 0)} onfocus={() => (hover = v)} onblur={() => (hover = 0)}
              onclick={() => onpick?.(v)}>{v}</button>
    {/each}
  </div>
  <div class="rr-hint muted">{hover ? hover + '/10 = ' + (hover / 2) + ' stars' : '1 = awful · 6 = fine · 8 = loved it · 10 = all-time'}</div>
</div>

<style>
  .rr-row { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 4px; }
  .rr-b { min-height: 44px; min-width: 0; border-radius: var(--r-sm); border: 1px solid var(--line); cursor: pointer;
          background: var(--bg-sunken); color: var(--text-strong); font-weight: 700; font-size: 15px;
          font-variant-numeric: tabular-nums; padding: 0; }
  .rr-b:hover:not(:disabled), .rr-b:focus-visible { border-color: var(--info); background: rgba(88, 166, 255, 0.14); outline: none; }
  .rr-b.hi:hover:not(:disabled), .rr-b.hi:focus-visible { border-color: var(--ok); background: rgba(63, 185, 80, 0.16); }
  .rr-b.lo:hover:not(:disabled), .rr-b.lo:focus-visible { border-color: var(--bad); background: rgba(248, 81, 73, 0.12); }
  .rr-b:disabled { opacity: 0.5; cursor: default; }
  .rr-hint { font-size: 11px; margin-top: 4px; min-height: 15px; }
  .rr-row.compact { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  @media (max-width: 480px) { .rr-row { grid-template-columns: repeat(5, minmax(0, 1fr)); } }   /* >= 44 px tap targets on a phone */
</style>
