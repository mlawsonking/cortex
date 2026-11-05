<script>
  // Thumbs on every Streaming Best / Missed Gems pick (taste loop). Up = a light seed, down = half a dislike AND the
  // title is hidden from the page (decision D3) until undone - the parent filters on thumbOf(key) === 'down' and
  // renders the inline undo. Server-side, taste-feedback only accepts titles on a CURRENT page contract.
  import { thumb, thumbOf } from '../lib/taste.svelte.js';
  import { actionsEnabled } from '../lib/act.js';

  let { tkey, title = '' } = $props();
  let busy = $state(false);
  let err = $state('');
  const cur = $derived(thumbOf(tkey));

  async function set(sig) {
    if (busy) return;
    busy = true; err = '';
    try { await thumb(tkey, cur === sig ? 'clear' : sig); }
    catch (e) { err = String(e?.message ?? e).replace(/^ERR: /, ''); }
    finally { busy = false; }
  }
</script>

{#if actionsEnabled && tkey}
  <span class="th">
    <button class="th-b" class:on={cur === 'up'} disabled={busy} onclick={() => set('up')}
            aria-pressed={cur === 'up'} aria-label={'More like ' + title} title="more like this">&#128077;</button>
    <button class="th-b" class:on={cur === 'down'} disabled={busy} onclick={() => set('down')}
            aria-pressed={cur === 'down'} aria-label={'Not for me: ' + title} title="not for me (hides it)">&#128078;</button>
    {#if err}<span class="act-msg err">{err}</span>{/if}
  </span>
{/if}

<style>
  .th { display: inline-flex; gap: 4px; align-items: center; }
  .th-b { min-width: 40px; min-height: 36px; border-radius: 999px; border: 1px solid var(--line); cursor: pointer;
          background: var(--chip-bg); font-size: var(--fs-md); line-height: 1; padding: 0 8px; filter: grayscale(0.6); }
  .th-b:hover:not(:disabled), .th-b:focus-visible { border-color: var(--info); filter: none; }
  .th-b.on { border-color: var(--ok); background: var(--ok-tint); filter: none; }
  .th-b:disabled { opacity: 0.6; }
</style>
