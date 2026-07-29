<script>
  import { Contract, clock } from './lib/contracts.svelte.js';
  import TonightPick from './cards/TonightPick.svelte';
  import Services from './cards/Services.svelte';
  import Storage from './cards/Storage.svelte';

  // One clock for every age badge; one Contract per card. Nothing here reaches outside the origin.
  const tick = clock();
  const pick = new Contract('tonight-pick');
  const services = new Contract('services');
  const storage = new Contract('storage');

  $effect(() => tick.start());
  $effect(() => pick.start());
  $effect(() => services.start());
  $effect(() => storage.start());
</script>

<div class="top">
  <div>
    <div class="brand">Cortex &middot; Media Brain</div>
    <div class="brand-sub">
      DESKTOP-VSRO8KT &middot; contract-backed &middot; <a href="/">legacy dashboard &rarr;</a>
    </div>
  </div>
</div>

<div class="grid">
  <TonightPick contract={pick} now={tick.now} />
  <Services contract={services} now={tick.now} />
  <Storage contract={storage} now={tick.now} />
</div>

<div class="foot">
  P1 &middot; 3 of 20 contracts rendered &middot; every card shows the age of its own data
</div>
