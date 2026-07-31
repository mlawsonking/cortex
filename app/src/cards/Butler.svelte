<script>
  // Butler: hands a free-text message to the existing ntfy butler pipeline via /act/butler.
  //
  // The text is DATA, not a command this app interprets. It is forwarded to the same butler the phone talks to,
  // which classifies it with claude -p under locked flags (--max-turns 1, --allowedTools "", neutral cwd) and
  // then maps the result onto its own server-side verb allow-list. Nothing typed here reaches a shell.
  import { act, actionsEnabled } from '../lib/act.js';

  let text = $state('');
  let busy = $state(false);
  let reply = $state('');
  let err = $state(false);

  async function send(e) {
    e.preventDefault();
    const msg = text.trim();
    if (!msg) return;
    busy = true; reply = ''; err = false;
    try {
      reply = await act('butler', 'msg=' + encodeURIComponent(msg));
      text = '';
    } catch (ex) {
      reply = String(ex?.message ?? ex); err = true;
    } finally {
      busy = false;
    }
  }
</script>

<section class="card">
  <div class="card-head"><h2 class="card-title">Butler</h2></div>
  {#if actionsEnabled}
    <form onsubmit={send}>
      <input class="field" bind:value={text} autocomplete="off" placeholder="pause downloads &middot; what's on tonight" />
      <button class="btn" style:margin-top="8px" type="submit" disabled={busy}>{busy ? 'sending...' : 'send'}</button>
    </form>
    {#if reply}<div class="act-msg" class:err style:margin-top="8px">{reply}</div>{/if}
  {:else}
    <div class="muted">actions are disabled (read-only mode)</div>
  {/if}
</section>
