<script>
  // Home card "Rate what you watched" - the top 3 titles by leverage from the rate-queue contract, two taps each.
  // Optimistic: a tap flips the row to "you said 7 · Cortex guessed 8" (the guess is hidden until then - no
  // anchoring), then the next title slides in. A failed save rolls back with a visible retry; nothing is lost
  // silently. The server re-checks every key (rate-queue allow-list or a live library lookup).
  import Card from './Card.svelte';
  import RateRow from './RateRow.svelte';
  import { rate } from '../lib/taste.svelte.js';
  import { actionsEnabled } from '../lib/act.js';

  let { contract, now } = $props();

  let gone = $state({});        // key -> true once answered (hidden locally until the contract catches up)
  let flip = $state({});        // key -> {value, guess} while the reveal shows
  let err = $state({});         // key -> message
  let busy = $state({});

  async function pick(r, v) {
    if (busy[r.key]) return;
    busy[r.key] = true; err[r.key] = '';
    try {
      const out = await rate(r.key, String(v), 'rate');
      flip[r.key] = { value: v, guess: out.guess };
      setTimeout(() => { gone[r.key] = true; delete flip[r.key]; }, 1200);
    } catch (e) {
      err[r.key] = "didn't save - " + String(e?.message ?? e).replace(/^ERR: /, '') + ' (tap a number to retry)';
    } finally {
      busy[r.key] = false;
    }
  }
</script>

<Card title="Rate what you watched" {contract} {now}>
  {#snippet body(d)}
    {@const open = d.items.filter((r) => !gone[r.key])}
    {#if !open.length}
      <div class="rq-empty">All caught up. <span class="muted">Cortex accuracy {d.eval.rho ?? '?'}
        (baseline {d.eval.baseline_rho ?? '?'})</span></div>
    {:else}
      <div class="muted rq-lede">Your rating teaches every recommendation. Highest-leverage first.</div>
      {#each open.slice(0, 3) as r (r.key)}
        <div class="rq-item" class:flipped={flip[r.key]}>
          <img class="rq-poster" loading="lazy" alt="" src={'/photo?key=' + encodeURIComponent(r.thumb) + '&width=150'} />
          <div class="rq-body">
            <div class="rq-title">{r.title} <span class="muted">{r.year ?? ''}</span>
              {#if r.type === 'tv'}<span class="kind">show</span>{/if}</div>
            <div class="rq-why muted">{r.reasons.join(' · ')}</div>
            {#if flip[r.key]}
              <div class="rq-flip">you said <strong>{flip[r.key].value}</strong>
                {#if flip[r.key].guess} · Cortex guessed <strong>{flip[r.key].guess}</strong>{/if}</div>
            {:else if actionsEnabled}
              <RateRow compact title={r.title} disabled={busy[r.key]} onpick={(v) => pick(r, v)} />
              {#if err[r.key]}<div class="act-msg err">{err[r.key]}</div>{/if}
            {:else}
              <div class="muted">rating is off: actions are switched off (wg\brain\ACTIONS-OFF)</div>
            {/if}
          </div>
        </div>
      {/each}
      <a class="rq-more" href="#/rate">backlog {d.backlog.total} · {d.backlog.high_leverage} high-leverage &rarr; clear it</a>
    {/if}
  {/snippet}
</Card>

<style>
  .rq-lede { font-size: 12px; margin-bottom: 8px; }
  .rq-item { display: flex; gap: 10px; padding: 8px 0; border-top: 1px solid var(--line-soft); transition: opacity 0.3s; }
  .rq-item:first-of-type { border-top: 0; }
  .rq-item.flipped { opacity: 0.85; }
  .rq-poster { width: 46px; height: 69px; flex: 0 0 auto; object-fit: cover; border-radius: var(--r-sm);
               background: var(--bg-sunken); border: 1px solid var(--line); }
  .rq-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .rq-title { font-weight: 600; color: var(--text-strong); }
  .rq-why { font-size: 11px; }
  .rq-flip { font-size: 14px; padding: 10px 0; color: var(--text-strong); }
  .rq-more { display: inline-block; margin-top: 8px; font-size: 12px; color: var(--info); text-decoration: none; }
  .rq-empty { padding: 8px 0; }
  .kind { font-size: 9px; text-transform: uppercase; letter-spacing: 0.8px; padding: 1px 6px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--accent); margin-left: 4px; vertical-align: 2px; }
</style>
