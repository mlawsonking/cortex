<script>
  // I4 H&R Horizon, problems-only (M3 verdict 2026-08-14): Michael does not want ratio-progress tables -
  // only "is any under-ratio torrent NOT seeding properly". The contract still carries the full trajectory
  // data (trackers/risk_feed) for anything else that wants it; this card renders exceptions or an all-clear.
  // Read-only forever, like the sentinel: visibility, not verbs. Announce-silence is invisible to qBit state;
  // the audit's check-hnr-exposure self-heal owns that class and pushes on it.
  import Card from './Card.svelte';

  let { contract, now } = $props();
</script>

<Card title="H&amp;R horizon" {contract} {now}>
  {#snippet body(d)}
    {#if (d.problems ?? []).length === 0}
      <div class="allclear">
        <span class="ok-dot"></span>
        all under-ratio torrents are seeding properly
      </div>
      <div class="muted">
        {d.totals.below_goal} below 1.0 goal, {(d.totals.remaining_gb / 1000).toFixed(1)} TB to repay -
        all actively announcing/seeding; nothing needs you
      </div>
    {:else}
      <div class="probhead k-failed">{d.problems.length} under-ratio torrent{d.problems.length === 1 ? '' : 's'} NOT seeding properly</div>
      {#each d.problems as p, i (p.name + i)}
        <div class="prow">
          <div class="ptitle">{p.name}</div>
          <div class="pmeta muted">{p.tracker.split('.')[0]} &middot; ratio {p.ratio.toFixed(2)} &middot; {p.remaining_gb.toFixed(1)} GB owed &middot; state: <span class="k-failed">{p.state}</span></div>
        </div>
      {/each}
      <div class="muted" style:margin-top="6px">
        fix path: resume/force-start in qBit, or wait for the audit self-heal cycle (it force-starts silent ones)
      </div>
    {/if}
  {/snippet}
</Card>

<style>
  .allclear { display: flex; align-items: center; gap: 8px; padding: 4px 0 6px; }
  .ok-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--ok); display: inline-block; }
  .probhead { margin-bottom: 6px; }
  .prow { padding: 4px 0; border-top: 1px solid var(--line-soft); }
  .ptitle { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pmeta { font-size: var(--fs-xs); }
</style>
