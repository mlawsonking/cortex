<script>
  // 4K upgrade advisor. EACH button is one real download - the server monitors that single title, switches it to
  // the UHD-Efficient profile (Remux excluded, x265 preferred, 2160p capped at 350 MB/min) and searches it. Never
  // bulk. The existing 1080p file is kept until the 4K import lands.
  //
  // blocked_disk=true means the producer's disk guard forbids it: the button is NOT rendered at all rather than
  // rendered-and-disabled, so there is nothing to click through.
  import Card from './Card.svelte';
  import ActionBtn from './ActionBtn.svelte';
  import { actionsEnabled } from '../lib/act.js';

  let { contract, now } = $props();
</script>

<Card title="4K upgrade advisor" {contract} {now} span={true}>
  {#snippet body(d)}
    {#each d.slice(0, 8) as u (u.radarrId)}
      <div class="li">
        <span class="li-main">{u.title}</span>
        <span class="li-side">rated {u.rating ?? '-'} &middot; {u.current_res ?? '?'} &middot; ~{u.est_gb ?? '?'} GB</span>
        {#if u.blocked_disk}
          <span class="li-side k-failed">disk guard</span>
        {:else}
          <ActionBtn label="&rarr; 4K" verb="upgrade4k" body={'id=' + u.radarrId}
                     busyLabel="grabbing" title="Monitors and searches this ONE title in the UHD-Efficient profile" />
        {/if}
      </div>
    {/each}

    <div class="muted" style:margin-top="8px">
      {d.length} candidates ranked by your own rating.
      {#if actionsEnabled}Each click is one real download, and you are the only trigger.{/if}
      1080p is kept until the 4K actually imports.
    </div>
  {/snippet}
</Card>
