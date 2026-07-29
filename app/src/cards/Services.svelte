<script>
  import Card from './Card.svelte';
  import { act } from '../lib/act.js';

  let { contract, now } = $props();

  // Mirrors the server's OWN restart allow-list (ALLOW_SVCS in dashboard-server.py). This list only decides
  // whether to OFFER the button - the server re-checks and refuses anything not on its list, so a tampered
  // client gains nothing. Storage / VPN / torrent / OS services are absent by design and must stay absent.
  const FIXABLE = new Set(['Sonarr', 'Radarr', 'Prowlarr', 'Bazarr', 'Tautulli', 'FlareSolverr']);

  let busy = $state('');
  let msg = $state('');
  let msgErr = $state(false);

  async function fix(name) {
    busy = name; msg = ''; msgErr = false;
    try {
      msg = await act('restart-service', 'svc=' + encodeURIComponent(name));
      await contract.refresh();
    } catch (e) {
      msg = String(e?.message ?? e); msgErr = true;
    } finally {
      busy = '';
    }
  }
</script>

<Card title="Services" {contract} {now}>
  {#snippet body(d)}
    <div class="row" style:margin-bottom="10px">
      <strong class="mono" style:font-size="20px" style:color="var(--text-strong)">{d.up_count}/{d.total}</strong>
      <span class="muted">up</span>
    </div>

    <div class="rowgrid">
      {#each d.services as s (s.name)}
        <div class="row">
          <span class="dot" class:ok={s.up} class:bad={!s.up}></span>
          <span class="row-name">{s.name}</span>
          {#if !s.up && FIXABLE.has(s.name)}
            <button class="btn ghost" disabled={busy === s.name} onclick={() => fix(s.name)}>
              {busy === s.name ? '...' : 'restart'}
            </button>
          {/if}
        </div>
      {/each}
    </div>

    <div class="row" style:margin-top="12px">
      {#if d.vpn_bound === true}
        <span class="dot ok"></span><span>VPN-bound &mdash; kill-switch armed</span>
      {:else if d.vpn_bound === false}
        <span class="dot bad"></span><span>NOT VPN-bound</span>
      {:else}
        <span class="dot unk"></span><span>VPN binding <em>unknown</em> &mdash; qBit did not answer</span>
      {/if}
    </div>

    {#if msg}
      <div class="act-msg" class:err={msgErr} style:margin-top="8px">{msg}</div>
    {/if}
  {/snippet}
</Card>
