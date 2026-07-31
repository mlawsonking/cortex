<script>
  // Every action in this app goes through here, so the kill-flag, the busy state and honest error reporting are
  // enforced in ONE place rather than remembered per card.
  //
  // The client is not a security boundary and this component does not pretend to be one: it decides what to
  // OFFER. The server re-checks the verb against its own allow-list and refuses anything else no matter what we
  // send, which is why no verb reachable from here can remove a torrent, unmonitor, or delete.
  import { act, actionsEnabled } from '../lib/act.js';

  let { label, verb, body = '', busyLabel = '...', done = null, title = '' } = $props();

  let busy = $state(false);
  let msg = $state('');
  let err = $state(false);

  async function go() {
    busy = true; msg = ''; err = false;
    try {
      const reply = await act(verb, body);
      msg = reply.slice(0, 40);
      if (done) await done(reply);
    } catch (e) {
      msg = String(e?.message ?? e); err = true;
    } finally {
      busy = false;
    }
  }
</script>

{#if actionsEnabled}
  <button class="btn" disabled={busy} onclick={go} {title}>{busy ? busyLabel : label}</button>
  {#if msg}<span class="act-msg" class:err>{msg}</span>{/if}
{/if}
