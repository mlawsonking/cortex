<script>
  // "Watch tonight": puts an owned title into the Plex playlist "Cortex: Tonight" (a show queues its first unwatched
  // episode). Server-side, queue-watch only accepts rating keys on the current Missed Gems / Tonight's Pick
  // contracts, refuses duplicates and caps the playlist at 10, and verifies by re-reading the playlist. Media is
  // never touched.
  import { queueWatch } from '../lib/taste.svelte.js';
  import { actionsEnabled } from '../lib/act.js';

  let { ratingKey, title = '' } = $props();
  let state = $state('idle');     // idle | busy | queued | error
  let msg = $state('');

  async function go() {
    state = 'busy'; msg = '';
    try {
      const out = await queueWatch(ratingKey);
      state = 'queued'; msg = out.queued;
    } catch (e) {
      const m = String(e?.message ?? e).replace(/^ERR: /, '');
      if (m.startsWith('already in')) { state = 'queued'; msg = title; }
      else { state = 'error'; msg = m; }
    }
  }
</script>

{#if state === 'queued'}
  <span class="chip ok" title={'Plex > Playlists > Cortex: Tonight - ' + msg}>&#9654; in tonight's playlist</span>
{:else if actionsEnabled && ratingKey}
  <button class="btn ghost wb" disabled={state === 'busy'} onclick={go} aria-label={'Queue ' + title + ' for tonight in Plex'}
          title="Adds it to the Plex playlist 'Cortex: Tonight' (shows: the first unwatched episode)">
    {state === 'busy' ? 'queuing...' : '▶ Tonight'}</button>
  {#if state === 'error'}<span class="act-msg err">{msg}</span>{/if}
{/if}

<style>
  .wb { min-height: 36px; }
  .chip { display: inline-block; font-size: 11px; font-weight: 600; padding: 4px 9px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--text-dim); background: rgba(255, 255, 255, 0.04); }
  .chip.ok { color: var(--ok); border-color: rgba(63, 185, 80, 0.4); background: rgba(63, 185, 80, 0.1); }
</style>
