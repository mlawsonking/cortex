<script>
  import { Contract, clock } from './lib/contracts.svelte.js';
  import { actionsEnabled } from './lib/act.js';
  import TonightPick from './cards/TonightPick.svelte';
  import Oracle from './cards/Oracle.svelte';
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
  import HnR from './cards/HnR.svelte';
  import Upgrades from './cards/Upgrades.svelte';
  import Passport from './cards/Passport.svelte';
  import Recs from './cards/Recs.svelte';
  import Butler from './cards/Butler.svelte';
  import AskMood from './cards/AskMood.svelte';
  import Rhythm from './cards/Rhythm.svelte';
  import Ledger from './cards/Ledger.svelte';
  import Horizon from './cards/Horizon.svelte';
  import DeadShelf from './cards/DeadShelf.svelte';
  import CoupleCompat from './cards/CoupleCompat.svelte';

  // One clock for every age badge; one Contract per card. Nothing here reaches outside the origin.
  // Card order IS priority order, because on a phone this is a single column.
  const tick = clock();
  const pick = new Contract('tonight-pick');
  const oracle = new Contract('oracle', 60000);
  const services = new Contract('services');
  const storage = new Contract('storage');
  const plexNow = new Contract('plex-now');
  const pipeline = new Contract('pipeline');
  const hnr = new Contract('hnr');
  const drives = new Contract('smart', 60000);
  const library = new Contract('library-stats');
  const health = new Contract('health');
  const security = new Contract('security', 60000);
  const calendar = new Contract('calendar', 60000);
  const activity = new Contract('activity');
  const upgrades = new Contract('upgrades', 300000);
  const passport = new Contract('passport', 300000);
  const recs = new Contract('recs', 300000);
  const rhythm = new Contract('rhythm', 300000);
  const ledger = new Contract('ledger', 300000);
  const horizon = new Contract('hnr-horizon', 300000);
  const deadShelf = new Contract('dead-shelf', 300000);
  const coupleCompat = new Contract('couple-compat', 300000);

  const all = [pick, oracle, services, storage, plexNow, pipeline, hnr, drives, library,
               health, security, calendar, activity, upgrades, passport, recs, rhythm, ledger, horizon,
               deadShelf, coupleCompat];

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
  {#if !actionsEnabled}
    <div class="readonly">
      <strong>Read-only mode.</strong> Every action button is hidden because <code>wg\brain\ACTIONS-OFF</code>
      exists. Delete that file to re-enable. The server's verb allow-list was never changed.
    </div>
  {/if}

  <TonightPick contract={pick} now={tick.now} />
  <Rhythm contract={rhythm} now={tick.now} />
  <CoupleCompat contract={coupleCompat} now={tick.now} />
  <Oracle contract={oracle} now={tick.now} />
  <Services contract={services} now={tick.now} />
  <Storage contract={storage} now={tick.now} />
  <NowPlaying contract={plexNow} now={tick.now} />
  <Pipeline contract={pipeline} now={tick.now} />
  <HnR contract={hnr} now={tick.now} />
  <Horizon contract={horizon} now={tick.now} />
  <Ledger contract={ledger} now={tick.now} />
  <DeadShelf contract={deadShelf} now={tick.now} />
  <Drives contract={drives} now={tick.now} />
  <Library contract={library} now={tick.now} />
  <Health contract={health} now={tick.now} />
  <Security contract={security} now={tick.now} />
  <Butler />
  <AskMood />
  <Calendar contract={calendar} now={tick.now} />
  <Activity contract={activity} now={tick.now} />
  <Upgrades contract={upgrades} now={tick.now} />
  <Passport contract={passport} now={tick.now} />
  <Recs contract={recs} now={tick.now} />
  <RecentlyAdded contract={plexNow} now={tick.now} />
</div>

<div class="foot">
  P4 &middot; 21 contracts rendered &middot; every card shows the age of its own data
</div>
