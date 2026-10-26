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
  import CoupleCompat from './cards/CoupleCompat.svelte';
  import GapRadar from './cards/GapRadar.svelte';
  import TasteVelocity from './cards/TasteVelocity.svelte';
  import AnomalyFeed from './cards/AnomalyFeed.svelte';
  import Wrapped from './cards/Wrapped.svelte';
  import CostQuality from './cards/CostQuality.svelte';
  import StreamingBest from './pages/StreamingBest.svelte';
  import MissedGems from './pages/MissedGems.svelte';

  // Hash routing (2026-10-26): #/ = the cards, #/streaming = Streaming Best, #/missed = Missed Gems. Pure client
  // side - no server route, no CSP change; the pages fetch their own contracts through the same /v2/data/ route.
  function parseRoute(h) {
    const r = String(h || '').replace(/^#\/?/, '').split(/[?/]/)[0];
    return r === 'streaming' || r === 'missed' ? r : 'cards';
  }
  let route = $state(parseRoute(location.hash));
  $effect(() => {
    const on = () => { route = parseRoute(location.hash); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  });

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
  const coupleCompat = new Contract('couple-compat', 300000);
  const gapRadar = new Contract('gap-radar', 300000);
  const tasteVelocity = new Contract('taste-velocity', 300000);
  const anomalyFeed = new Contract('anomaly-feed', 300000);
  const wrapped = new Contract('wrapped', 300000);
  const costQuality = new Contract('cost-of-quality', 300000);

  const all = [pick, oracle, services, storage, plexNow, pipeline, hnr, drives, library,
               health, security, calendar, activity, upgrades, passport, recs, rhythm, ledger, horizon,
               coupleCompat, gapRadar, tasteVelocity, anomalyFeed, wrapped, costQuality];

  $effect(() => tick.start());
  $effect(() => {
    if (route !== 'cards') return;          // the card contracts only poll while the cards are on screen
    const stops = all.map((c) => c.start());
    return () => stops.forEach((s) => s());
  });
</script>

<div class="top">
  <div>
    <div class="brand">Cortex &middot; Media Brain</div>
    <div class="brand-sub">DESKTOP-VSRO8KT &middot; contract-backed</div>
  </div>
  <nav class="nav">
    <a href="#/" class:on={route === 'cards'}>Cortex</a>
    <a href="#/streaming" class:on={route === 'streaming'}>Streaming Best</a>
    <a href="#/missed" class:on={route === 'missed'}>Missed Gems</a>
    <a href="/legacy/" class="legacy">legacy &rarr;</a>
  </nav>
</div>

{#if route === 'streaming'}
<div class="grid"><StreamingBest /></div>
{:else if route === 'missed'}
<div class="grid"><MissedGems /></div>
{:else}
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
  <Wrapped contract={wrapped} now={tick.now} />
  <Services contract={services} now={tick.now} />
  <Storage contract={storage} now={tick.now} />
  <NowPlaying contract={plexNow} now={tick.now} />
  <Pipeline contract={pipeline} now={tick.now} />
  <HnR contract={hnr} now={tick.now} />
  <Horizon contract={horizon} now={tick.now} />
  <AnomalyFeed contract={anomalyFeed} now={tick.now} />
  <Ledger contract={ledger} now={tick.now} />
  <CostQuality contract={costQuality} now={tick.now} />
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
  <GapRadar contract={gapRadar} now={tick.now} />
  <TasteVelocity contract={tasteVelocity} now={tick.now} />
  <Recs contract={recs} now={tick.now} />
  <RecentlyAdded contract={plexNow} now={tick.now} />
</div>

{/if}

<div class="foot">
  {route === 'cards' ? '25 contracts on the cards' : route === 'streaming' ? 'streaming-best contract' : 'missed-gems contract'}
  &middot; every view shows the age of its own data
</div>
