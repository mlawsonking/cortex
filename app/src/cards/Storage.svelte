<script>
  import Card from './Card.svelte';
  import { bytes, pct, fillClass } from '../lib/fmt.js';

  let { contract, now } = $props();

  const PARITY = {
    synced:  { cls: 'ok',  text: 'protected' },
    syncing: { cls: 'unk', text: 'rebuilding parity' },
    stale:   { cls: 'bad', text: 'STALE - sync needed' }
  };
</script>

<Card title="Storage" {contract} {now}>
  {#snippet body(d)}
    {#each d.disks as k (k.letter)}
      {@const p = pct(k.used, k.total)}
      <div class="bar-row">
        <div class="bar-label">
          {k.letter}:
          <span class="muted">{k.label ? k.label + ' ' : ''}{bytes(k.free)} free{k.removable ? ' · USB' : ''}</span>
        </div>
        <div class="bar">
          {#if p !== null}<div class="bar-fill {fillClass(p)}" style:width={p + '%'}></div>{/if}
        </div>
        <div class="bar-pct">{p === null ? '-' : Math.round(p) + '%'}</div>
      </div>
    {/each}

    {#if d.parity}
      {@const s = PARITY[d.parity.state] ?? { cls: 'unk', text: d.parity.state }}
      <div class="row" style:margin-top="12px">
        <span class="dot {s.cls}"></span>
        <span>SnapRAID parity: <strong>{s.text}</strong></span>
        {#if d.parity.state === 'syncing' && d.parity.pct !== null}
          <span class="muted mono">{d.parity.pct}%</span>
        {/if}
      </div>
      <div class="muted" style:margin-top="4px">
        {#if d.parity.last_sync_age_h === null}
          no successful-sync record found
        {:else}
          last successful sync {d.parity.last_sync_age_h < 1 ? 'under an hour' : Math.round(d.parity.last_sync_age_h) + 'h'} ago
          {#if d.parity.sync_source === 'flag'}
            <span class="k-failed">(marker file only &mdash; no completion record in the log)</span>
          {/if}
        {/if}
        {#if d.parity.pfree !== null}&middot; parity drive {bytes(d.parity.pfree)} free{/if}
      </div>
    {:else}
      <div class="muted" style:margin-top="12px">parity state unavailable</div>
    {/if}

    {#if d.forecast}
      <div class="muted" style:margin-top="8px">{d.forecast}</div>
    {/if}
  {/snippet}
</Card>
