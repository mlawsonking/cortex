<script>
  // Add-to-library button for the Streaming Best page - the first buttons in this app that spend disk.
  // One click = Radarr/Sonarr add, monitored, search fired NOW (Michael's decision 2). The client is still not a
  // security boundary: it sends only the tmdb id, and dashboard-server.py / library_add.py re-check everything
  // (id must be on the CURRENT streaming-best contract, ACTIONS-OFF, rate limit, G:/D: disk bars, duplicate,
  // verify-by-effect). The server's reply is JSON on success and "ERR: ..." otherwise; act() throws on ERR.
  import { act, actionsEnabled } from '../lib/act.js';

  let { type, tmdb } = $props();

  let state = $state('idle');      // idle | busy | added | inlib | error
  let msg = $state('');

  async function go() {
    state = 'busy'; msg = '';
    try {
      const reply = JSON.parse(await act(type === 'tv' ? 'add-series' : 'add-movie', 'id=' + tmdb));
      if (reply && reply.added === true) { state = 'added'; msg = type === 'tv' ? 'Sonarr id ' + reply.id : 'Radarr id ' + reply.id; }
      else { state = 'error'; msg = 'server did not confirm the add'; }
    } catch (e) {
      const m = String(e?.message ?? e);
      if (m.startsWith('ERR: already in')) { state = 'inlib'; msg = m.replace(/^ERR: /, ''); }
      else { state = 'error'; msg = m.replace(/^ERR: /, ''); }
    }
  }
</script>

{#if state === 'added'}
  <span class="chip ok" title={msg}>added &#10003; &middot; searching</span>
{:else if state === 'inlib'}
  <span class="chip" title={msg}>in library &#10003;</span>
{:else if actionsEnabled}
  <button class="btn" disabled={state === 'busy'} onclick={go}
          title={type === 'tv' ? 'Add to Sonarr (all seasons monitored) and search now' : 'Add to Radarr (monitored) and search now'}>
    {state === 'busy' ? 'adding...' : type === 'tv' ? '+ add show' : '+ add film'}
  </button>
  {#if state === 'error'}<span class="act-msg err">{msg}</span>{/if}
{/if}

<style>
  .chip { display: inline-block; font-size: var(--fs-xs); font-weight: 600; padding: 4px 9px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--text-dim); background: var(--chip-bg); }
  .chip.ok { color: var(--ok); border-color: var(--ok-line); background: var(--ok-tint); }
</style>
