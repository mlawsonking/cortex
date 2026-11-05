<script>
  // I8 Anomaly Feed - the cross-system view. Every other health card answers "is THIS system ok?"; this one
  // answers "are these unrelated-looking events all pointing at the same indexer or tracker?".
  //
  // READ-ONLY BY CONSTRUCTION (v1 is actionless): retry / blocklist / disable-indexer verbs do not exist
  // server-side, and a new verb needs its own security review plus Michael's approval before a button may
  // appear here. Evidence is always rendered with the anomaly - a bare "anomaly" with no counts behind it is
  // exactly the plausible-looking claim this rebuild exists to kill. The sources note is likewise never
  // hidden: an all-clear on a partial read is not an all-clear, and the contract refuses to call it one.
  import Card from './Card.svelte';

  let { contract, now } = $props();

  const LABEL = {
    'indexer-failures': 'indexer',
    'stall-cluster': 'tracker stalls',
    'error-state': 'error state',
  };
</script>

<Card title="Anomaly feed" {contract} {now} span={true}>
  {#snippet body(d)}
    {#if d.all_clear}
      <div class="allclear">
        <span class="ok-dot"></span>
        no cross-system clustering
      </div>
      <div class="muted">
        no indexer is over-represented in the last 48h of grab/import failures, and no tracker is holding a
        cluster of stalled or errored downloads
      </div>
    {:else}
      {#if d.anomalies.length === 0}
        <div class="probhead k-other">
          nothing found in what could be read &mdash; but a source failed, so this is a partial view, not an all-clear
        </div>
      {:else}
        <div class="probhead k-failed">
          {d.anomalies.length} correlated anomal{d.anomalies.length === 1 ? 'y' : 'ies'}
          <span class="muted">
            ({d.anomalies.filter((a) => a.severity === 'warn').length} warn)
          </span>
        </div>
        {#each d.anomalies as a, i (a.type + a.subject + i)}
          <div class="arow">
            <div class="ahead">
              <span class="sev {a.severity}">{a.severity}</span>
              <span class="asubject">{a.subject}</span>
              <span class="muted">{LABEL[a.type] ?? a.type} &middot; {a.count}</span>
            </div>
            <div class="muted aev">{a.evidence}</div>
          </div>
        {/each}
      {/if}
    {/if}

    <div class="muted sources">
      {#each d.checked_sources as s (s.name)}
        <div class="srow">
          <span class={s.ok ? 'k-imported' : 'k-failed'}>{s.ok ? 'read' : 'FAILED'}</span>
          <span class="sname">{s.name}</span>
          {#if s.detail}<span class="sdetail">{s.detail}</span>{/if}
        </div>
      {/each}
      <div class="foot">
        48h window, Radarr + Sonarr history pooled (indexers are shared through Prowlarr) &middot;
        read-only: retry / blocklist verbs need their own review before buttons appear here
      </div>
    </div>
  {/snippet}
</Card>

<style>
  .allclear { display: flex; align-items: center; gap: 8px; padding: 4px 0 6px; }
  .ok-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--ok); display: inline-block; }
  .probhead { margin-bottom: 6px; }
  .arow { padding: 5px 0; border-top: 1px solid var(--line-soft); }
  .ahead { display: flex; align-items: baseline; gap: 8px; font-size: var(--fs-sm); min-width: 0; }
  .asubject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sev {
    flex: 0 0 auto; font-size: var(--fs-xs); font-weight: 500;
    padding: 1px 5px; border-radius: 6px; border: 1px solid;
  }
  .sev.warn { color: var(--bad); border-color: var(--bad-line); background: var(--bad-tint); }
  .sev.info { color: var(--warn); border-color: var(--warn-line); background: var(--warn-tint); }
  .aev { margin-top: 2px; }
  .sources { margin-top: 10px; border-top: 1px solid var(--line-soft); padding-top: 6px; }
  .srow { display: flex; gap: 6px; min-width: 0; }
  .sname { flex: 0 0 auto; }
  .sdetail { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .foot { margin-top: 4px; }
</style>
