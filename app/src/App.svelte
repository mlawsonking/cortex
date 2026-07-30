<script>
  import { Contract, clock } from './lib/contracts.svelte.js';
  import TonightPick from './cards/TonightPick.svelte';
  import Services from './cards/Services.svelte';
  import Storage from './cards/Storage.svelte';
  import Drives from './cards/Drives.svelte';
  import Pipeline from './cards/Pipeline.svelte';
  import NowPlaying from './cards/NowPlaying.svelte';
  import RecentlyAdded from './cards/RecentlyAdded.svelte';
  import Library from './cards/Library.svelte';
  import Health from './cards/Health.svelte';
  import Security from './cards/Security.svelte';
  import Calendar from './cards/Calendar.svelte';
  import Activity from './cards/Activity.svelte';

  // One clock for every age badge; one Contract per card. Nothing here reaches outside the origin.
  // Card order IS the priority order, because on a phone this is a single column.
  const tick = clock();
  const pick = new Contract('tonight-pick');
  const services = new Contract('services');
  const storage = new Contract('storage');
  const plexNow = new Contract('plex-now');
  const pipeline = new Contract('pipeline');
  const drives = new Contract('smart', 60000);
  const library = new Contract('library-stats');
  const health = new Contract('health');
  const security = new Contract('security', 60000);
  const calendar = new Contract('calendar', 60000);
  const activity = new Contract('activity');

  const all = [pick, services, storage, plexNow, pipeline, drives, library, health, security, calendar, activity];

  $effect(() => tick.start());
  $effect(() => {
    const stops = all.map((c) => c.start());
    return () => stops.forEach((s) => s());
  });
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
  <NowPlaying contract={plexNow} now={tick.now} />
  <Pipeline contract={pipeline} now={tick.now} />
  <Drives contract={drives} now={tick.now} />
  <Library contract={library} now={tick.now} />
  <Health contract={health} now={tick.now} />
  <Security contract={security} now={tick.now} />
  <Calendar contract={calendar} now={tick.now} />
  <Activity contract={activity} now={tick.now} />
  <RecentlyAdded contract={plexNow} now={tick.now} />
</div>

<div class="foot">
  P2 &middot; 11 contracts rendered &middot; every card shows the age of its own data
</div>
