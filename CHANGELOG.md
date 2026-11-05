# Changelog - Cortex brain app

Semver on the app; each contract is versioned independently in `contracts\registry.json`.

## [taste-ledger 1.0.0 + rate-queue 1.0.0 + tonight-pick 1.3.0 + 3 verbs + #/rate] 2026-11-02 - Taste loop round 1
Spec `wg\GAMEPLAN-TASTE-LOOP-2026-11.md`; full write-up SERVER-AUDIT s83.
- New producers: `taste_ledger.py` (append-only ledger + Plex rating ingest + compile to ratings-effective.json /
  taste-signals.json), `taste_eval.py` (fixed-holdout accuracy + guess calibration), `rate_queue.py` (leverage-ranked
  rate queue with household filter: content rules + device x hour naive Bayes), `plex_rows.py` (4 Plex home-screen
  collections via the Plex API), `taste_daily.py` (daily chain runner).
- `taste_core.py` (additive): `ratings_source()` prefers ratings-effective (>= 400 rows, TASTE-LEDGER-OFF absent);
  TV ratings -> TV seeds (kids lanes ignored); thumbs-up seeds at 0.35; thumbs-down / bailed = 0.5-weight dislikes;
  blocked titles in `excluded()`; `build(rows=...)` for the eval's training split. Scoring math, floors, lanes unchanged.
  Pages now say which ratings source they used.
- Contracts: taste-ledger 1.0.0 + rate-queue 1.0.0 (new, client), tonight-pick 1.3.0 (additive: rating_key, match;
  discover mode = missed-gems). validate-contracts 34/34.
- Verbs rate-title / taste-feedback / queue-watch (`wg\dashboard\taste_verbs.py`), allow-verbs.baseline 19. Route
  `/taste-search` (read-only, tailnet).
- App: RateQuick card, RateQueue page (#/rate), RateRow, ThumbBtns, WatchBtn, lib/taste.svelte.js; thumbs on both
  pages, Tonight buttons, nav badge. Release 99ee24fb00bc.
- Tests: new `brain\tests\` (33 unittest cases, temp-dir isolated) + `smoke_taste_loop.py` = verify-brain check 7.
- Found while building: Windows lock-file "delete pending" raises PermissionError, not FileExistsError (V1.1 caught
  221 lost appends of 1000); Kometa rejects collection_order custom with an id list.

## [missed-gems 1.1.0 + server-side kill flag] 2026-10-26 - follow-ups

**Added - Missed Gems "Shows you haven't started"** (contract 1.1.0, additive `shows` list, top 5 by match). The first
run scored 79 never-started series and none reached the film-dominated landed/gems lists, so a page promised as
"shows and movies" silently read films-only. The page also states "N unwatched films and M unwatched series
considered". "1 days on the shelf" -> "1 day".

**Fixed - ACTIONS-OFF is now enforced by the server for EVERY /act verb.** It used to only hide /v2/ buttons; the
server (and the legacy pages, which call /act directly) kept executing every allow-listed verb. One check in
dashboard-server.py's /act dispatch returns 403 while the flag exists. Proven both ways (regen-now 403 / 200).
Release 0d8552c8267f; validate-contracts 32/32; verify-brain 5/5 exit 0.

## [streaming-best 1.0.0 + missed-gems 1.0.0 + add verbs + hash routing] 2026-10-26 - Two taste-personalized pages

Commissioned by Michael 2026-10-26; spec + his three locked decisions in `wg\GAMEPLAN-STREAMING-PAGES-2026-10.md`.

**Added - `producers\taste_core.py`** (import-only): one "is this michael?" scorer shared by both pages. Inputs that
already existed: 488 banked ratings (mean 8.52 - he rates high, so seeds are WEIGHTED by (rating-7)/3), the
taste-graph michael persona, taste-velocity heat (page 1 only, mild), directors/cast from his rated films' TMDB
credits, the 17 passport auteurs (read-only via gap_radar's parser) as a strong prior, and 8 binged series as TV
seeds. Match = keyword/people similarity to loved seeds (scaled by genre overlap) + genre weights + person affinity
+ Bayesian-weighted quality, x a language factor from his own ratings. Hard rules in code: 1987 film floor, no
Family/Kids/Children, animation only because HIS ratings open it, no docu/talk/reality. TMDB cached under
`data\cache\tmdb\` (first build ~1,250 lookups at 4/s; reruns ~all cached). Calibration lesson (first cut): with genre
overlap as an ADDITIVE similarity term, 403 loved seeds meant every pure Drama "matched" The Help at 1.0 - genre now
only scales keyword/people similarity, and fan-inflated 8.9-over-900-votes no longer outranks 8.1-over-9,000.

**Added - contract `streaming-best` v1.0.0** (`streaming_best.py`, SLO 35d, daily 07:20 task + monthly self-gate,
Wrapped pattern; also retries the AI pass daily if a run fell back). TMDB discover + trending inside ~18 months;
floors films >= 200 votes / 6.8, shows >= 100 / 7.2; films need a digital release; shows need a resolved tvdb id and,
if they premiered before the window, <= 5 seasons ("returning prestige", not season 11 of Chicago Med). Excludes
owned (any Radarr/Sonarr entry), rated, Plex-watched, Missed-Gems rows. Deterministic top 40 -> ONE claude -p
(subscription; --json-schema, --allowedTools "", neutral cwd, transient retry) picks 15-20 mixed + one "why" line;
any failure ships the deterministic order with `ai:false` + reason. Grounding fix: the digest now carries each seed's
rating and each person's source films after the first AI run credited a director with the wrong film.
First list (ai=true): 8 films / 10 shows from 337 candidates -> 136 survivors.

**Added - contract `missed-gems` v1.0.0** (`missed_gems.py`, SLO 9d, weekly Sat 06:50, deterministic). Films from
unwatched-pool (two-stage: cheap Plex-field prescore, TMDB-enrich the top 450 + all recent); shows read straight from
the Plex TV section (zero watched episodes). DEVIATION from the spec's "extend unwatched-pool to v1.2.0": that
contract is a top-level movie ARRAY and couple-compat's Date Night refresh would mis-read show rows, so TV is read
here instead and `tv_source` says so. hero-drop titles (curated for Nathaniel) excluded. First run: 674 scored, 10
landed (Moneyball, Erin Brockovich, Sleepers...), 15 gems (Oppenheimer, Casino, Magnolia, The Irishman, Heat...).

**Added - verbs `add-movie` / `add-series`** (first disk-spending verbs; baseline updated in this same change, 14 ->
16). All guards server-side in `wg\dashboard\library_add.py` (guarded import like beacon_store): ACTIONS-OFF honored
server-side, id must be a row of the CURRENT streaming-best contract with matching type (tvdb taken from the
contract), 5 adds/min, G: >= 90% refused, D: seed store < 1 TiB refused (extra guard = release-batch's hold),
duplicate refused, profile "x265 Compact 1080p" + roots `G:\Media\Movies` / `G:\Media\TV` resolved live by name/path,
tag `streaming-best`, verify-by-effect re-query. Log `wg\audit\library-add.log`.

**Added - app hash routing** (`#/` cards, `#/streaming`, `#/missed`) + header nav (Cortex / Streaming Best / Missed
Gems / legacy). Card contracts poll only on the cards route. Posters same-origin (producer /art/sb-*.jpg cache;
/photo proxy for Plex) - CSP unchanged. Legacy link fixed to `/legacy/` (it pointed at `/`, which is Cortex since P5).

**Verified by effect:** validate-contracts 32/32 exit 0; live /act proofs - bad nonce 401, unknown id refused,
ACTIONS-OFF refused (page meta flipped to 0), REAL add of Predator: Killer of Killers -> Radarr id 4371 monitored,
profile 7, tag streaming-best, MoviesSearch fired, grabbed 1080p WEBRip x265 5 s later; duplicate re-click refused;
Sonarr path dry-run with POST intercepted (correct body; verify-by-effect refused to claim success). Release
4c7fdfc76c91 leak-grep PASS; verify-brain 5/5 PASS exit 0; both pages render desktop + 375px, zero console errors;
tasks run rc 0 (Streaming Best self-gated skip, Missed Gems regenerated).

## [hnr-horizon] 2026-10-26 - Below-goal now honors BOTH legs of the house H&R bar

**Fixed - the Horizon card reported time-satisfied seeds as "problems."** The producer skipped only
`ratio >= 1.0`, so every torrent qBit legitimately stopped at its 90-day limit (2,160h seeded - five times the
400h house bar) still counted as below goal, and because stoppedUP is outside SEEDING_OK it ALSO landed in the
problems exceptions list. The card showed "25 under-ratio torrents NOT seeding properly" when every one of them
had its obligation met on the time leg; Monthly Wrapped inherited the same inflation ("1,057 below goal owing
5,272 GB"). hnr_horizon.py now skips `seeding_time >= 400h` at the same gate as the ratio check (TIME_GOAL_S,
matching private-tracker-hnr-policy and the Seed Janitor's bar). Honest numbers after the fix: 78 below goal,
490 GB remaining, 39 never-at-current-rate, **0 problems** - and all 78 are actively seeding. Wrapped picks up
the corrected totals at its next monthly run.

## [passport 1.1.0] 2026-08-16 - Curated filmography id repair + the 1987 floor moves where it was claimed to be

**Fixed - the Auteur passport card was scoring other films' ownership.** The curated `$FILMOGRAPHY` table in
`wg\audit\passport.ps1` had 109 of 264 TMDB ids resolving to a completely different film than their label
(600 'Duel' was Full Metal Jacket; 4147 'Revolutionary Road' was Road to Perdition; 273248 'American Sniper'
was Tarantino's The Hateful Eight) - invisible in the output because Resolve-Title prints the curated label
whenever an id is not in Radarr. Every id was re-resolved from the director's real TMDB directing credits
(the method gap_radar.py proved; Coen Brothers via Joel Coen + an Ethan Coen pass for Drive-Away Dolls),
keeping the curated title lists verbatim. All 264 titles resolved, 0 unmatched; 4 spot-check anchors
(Body of Lies 12113, Welcome to Marwen 351044, Meet the Feebles 8216, J. Edgar 88794) all hit.

**Fixed - the 1987 year floor now actually lives in the producer.** Passport.svelte and passport.schema.json
both claimed it did; passport.ps1 applied none. It now drops pre-1987 canon films from every total, tally and
missing[] list (35 films excluded, same rule as Gap Radar), driven by a new `$YEARBYID` table generated from
TMDB release dates in the same pass. A film with no year entry is dropped and counted in `films_undated`,
never guessed. Payload gains `year_floor` / `films_below_floor` / `films_undated` / `generated_note`
(additive -> contract 1.1.0). The curated table keeps its full pre-floor canon: it documents the human
judgement and gap_radar.py reuses it read-only (a FORMAT CONTRACT comment now marks the parse anchors).

**Verified by effect**
* `powershell -NoProfile -File passport.ps1` (PS 5.1, pure ASCII checked): 229 post-floor films = 264 - 35,
  0 undated, per-director tallies now match the real library (e.g. Spielberg 25/25 own, Coens 18/18).
* gap_radar.py rerun against the repaired source: **`curated_ids_wrong` 109 -> 0**, 16/16 directors,
  228 post-floor films (229 minus its known Joel-only Drive-Away Dolls unmatch), missing lists agree with
  passport's (Body of Lies, Welcome to Marwen, ...).
* wrap_files.py rewrapped only `passport`; validate-contracts.py: 30 contracts, 0 hard failures, exit 0.

## [P3] 2026-07-30 - Intelligence + actions, behind a kill-flag - awaiting GATE M2

**Added** - 7 cards: `Oracle` (score + brief + HEVC reclaim, proposal-only), `HnR` (structurally read-only),
`Upgrades` (4K advisor, one real download per click), `Passport`, `Recs`, `Butler`, `AskMood`. 19 cards over 16
contracts. `Services` and `TonightPick` were refactored onto the shared `ActionBtn`.

**Added - the action kill-flag.** Creating `wg\brain\ACTIONS-OFF` makes the server inject `0` into the
`actions-enabled` meta tag, and every action disappears on the next load. No rebuild, no release flip, no restart,
and the server's `/act` allow-list is untouched - it keeps refusing exactly what it always refused. The client
flag fails CLOSED: anything other than a literal `"1"` is read-only, so a missing or malformed tag can never be
read as permission.

**Design decisions worth keeping**
* `ActionBtn.svelte` is the single path to any verb, so the kill-flag, busy state and honest error reporting are
  structural instead of per-card.
* Ask & mood are gated by the kill-flag too. They mutate nothing, but they make the server run a model query, and
  a "read-only mode" that still causes work on the box would make the banner's claim false.
* No grab button on the Passport card: `/act/grab` needs a Radarr id and that contract carries only missing
  TITLES. A button that guessed an id is a way to grab the wrong film.
* No verb on the H&R card, ever. Any downloaded data - partial or complete - is a hit-and-run liability; the only
  sanctioned removal test is `downloaded == 0`, and it lives server-side.
* `blocked_disk` upgrade candidates render no button at all rather than a disabled one - nothing to click through.

**Verified by effect**
* 19 cards, zero console messages, no horizontal overflow. **The SNAPSHOT badge is now exercised on real data:**
  4K advisor and Auteur passport both read `snapshot - 27.2d ago`, which is exactly how old those producers'
  output is.
* Kill-flag both directions: with `ACTIONS-OFF` present -> **0 buttons, 0 inputs**, banner shown, all 19 cards
  still rendering live data; removed -> 12 buttons and 3 inputs return. Same bundle, no rebuild.
* Security: `delete-torrent` / `remove` / `unmonitor` / `qbit-delete` all 404 against the allow-list; a real verb
  with a bad nonce 401s; `/ask` returns a proposal-only answer.
* `upgrade4k` deliberately NOT fired - each click is one real download and that belongs to Michael at M2.

**Found, not caused:** `claude -p` on this box returns "Not logged in - Please run /login". That silently degrades
the Oracle brief ("AI offline - deterministic score only"), Ask & mood ("ai unavailable") and the
Media-Server-Daily-Audit task. Every one of them degrades HONESTLY rather than fabricating output, which is why it
never looked broken. Fix is Michael running `claude setup-token` (already sitting in the Vikunja inbox as #29).

## [P2] 2026-07-30 - The ops board, and the end of the stale-parity bug class

**Added** - 9 cards, all routed through `Card.svelte` so freshness stays structural: `Drives` (SMART),
`Pipeline`, `NowPlaying`, `RecentlyAdded`, `Library`, `Health`, `Security`, `Calendar`, `Activity`.
12 cards now render 11 contracts. Also `parity-check.py` - a side-by-side diff of the legacy page against the
contracts (both come from ONE gen-dashboard run, so any disagreement is a mapping bug in emit_ops).

**Fixed - the bug class P2 exists to kill.** Parity freshness was decided by whether
`snapraid-sync-complete.flag` EXISTED. That file is a one-off migration marker written 2026-07-03 and never
touched again, so for ~27 days the Storage card said **"protected"** while the Health card said **"Parity sync
648h ago"** - two widgets, one stale file, both wrong, contradicting each other in public. Parity is now decided
by the sync log's own completion line (`pulse.snapraid_last_ok`): `synced` means a sync SUCCEEDED within 48h.
Truth on this box: it synced today at 05:13, exit 0. Both the legacy page and v2 now say so, and both will flip
to stale the day it stops. The contract carries `last_sync_age_h` + `sync_source`, and a `flag`-only answer is
labelled as the weaker claim it is.

**Fixed - reading that log needed a second bug fixed first.** The first implementation still fell back to the
flag, because `wg\snapraid-sync.log` is **mixed-encoding**: snapraid's output is UTF-16LE (PowerShell redirect)
while the `=== nightly sync EXITED code=0 <iso> ===` markers are plain UTF-8. Decoded as UTF-16 the marker
becomes CJK mojibake, so a single-encoding reader literally cannot see it. `_tail_variants()` now tries UTF-16,
UTF-16 shifted one byte, and UTF-8, and takes the newest match from any of them.

**Fixed - the calendar was showing dates that contradicted its own heading.** A movie enters the 14-day window on
one of three release dates, but the producer displayed `digital || physical || inCinemas` in fixed priority.
*Barbarian* is in the window for its **2026-08-11 physical** release and was rendered as **2022-10-25**; three
more showed dates already past. It now picks the earliest date that is actually IN the window and names its kind
(digital / physical / in cinemas), dropping rows where none is. `dayLabel()` also shows the year whenever it is
not the current one - a bare "Tue, Oct 25" under a "next 14 days" heading reads as upcoming.

**Fixed - no silent caps.** The calendar renders at most 16 rows and said nothing about it (which is how
Barbarian's corrected row disappeared entirely). The contract now carries `total` and the card reads
"showing 16 of 27 in the next 14 days". `calendar` -> v1.1.0, `storage` -> v1.1.0.

**Improved - "not checked" is not "healthy".** A health probe reporting `n/a` could not run; the legacy board
painted those green beside genuine passes. They now render as unknown, with a count. Activity also collapses
ADJACENT identical events into one row with a count, so a retry storm reads as `x10` instead of ten rows - and
that count sits outside the truncating element, because on a phone the ellipsis was eating it.

**Verified by effect**
* `parity-check.py`: **20 values compared, 0 differ** - services, Plex/Radarr/Sonarr counts, queues, pipeline,
  every disk's free space, SMART row count, H&R row count.
* Validator 20/20 valid after both version bumps. 12 cards render, all badges fresh, 12 posters loaded with 0
  broken images, zero console messages, desktop 4-col and phone single-column with no page overflow.
* `snapraid_last_ok()` -> `source=log, 2026-07-30T05:13:09, age 8.4h`; Storage reads "last successful sync 8h
  ago"; the Parity-sync probe flipped from a 27-day-old false alarm to `True / 8h ago`.

## [P1] 2026-07-29 - Foundation + first light (`/v2/`) - awaiting GATE M1

**Added**
* `app\` - Svelte 5 + Vite static bundle. **3 direct deps, exact pins** (`svelte` 5.56.8, `vite` 8.1.5,
  `@sveltejs/vite-plugin-svelte` 7.2.0), 39 packages total, lockfile committed, `npm ci --ignore-scripts` only.
  Output: **19.2 kB gzip JS + 2.0 kB gzip CSS** (budget was <=200 kB gz). No chart library - the sparkline/bar
  work is hand-rolled SVG/CSS, keeping the budget at 3 of 5.
* `app\src\styles.css` - the design system: tokens for the existing palette (so it reads as the same product),
  systematised spacing/type scale, card + badge + bar + hero primitives, and an explicit phone block.
* `app\src\lib\contracts.svelte.js` - the only data path. Refuses anything that is not a `{_meta, data}` envelope,
  and turns `_meta` into exactly four honest states: `fresh` / `stale` / `snapshot` / `error`.
* `app\src\cards\Card.svelte` - the shell every card goes through, which is how the honesty rules became
  structural: badge comes from the contract's own `_meta`; a load failure renders an error state; and if refreshes
  start failing while a good envelope is still held, the card shows the good data **and says refreshes are
  failing** rather than passing last-known-good off as live.
* Cards: `TonightPick` (reroll via the existing verb), `Services` (restart buttons only for services the server's
  own allow-list accepts), `Storage` (disks + parity + fill forecast).
* `app\test\freshness.test.mjs` - 16 assertions on the freshness state machine, plain `node`, no test framework.
* `release.ps1` - build -> content-hash -> **leak-grep -> only then flip the junction**. Releases are immutable
  `releases\<hash>\` dirs; `/v2` is a junction; rollback is one flip. Writes `release.json` (per-file sha256) for
  P6's served-vs-built drift check, and `releases\ACTIVE.txt`.
* Producer-side art cache: `emit_ops._cache_art` fetches the TMDB backdrop **server-side** into
  `wg\dashboard\art\<tmdb>.jpg` (verified JPEG magic before publishing), so the page loads art same-origin and
  makes **zero external requests** under a strict CSP. Bounded by the recs pool (~30 files).
* `tonight-pick` contract -> **v1.1.0**: adds `tmdb` and `art_local`. The tmdb id is recovered by re-resolving
  `recs[idx % len]` exactly as gen-dashboard does, then **cross-checked on title** - on a mismatch both go null,
  so a wrong film's artwork can never be shown.

**Changed**
* `wg\dashboard\dashboard-server.py` (backup `.bak-preP1`, sha256
  D4271AF47EB2744F20D016D0861DF6ED36F5D75C216C8498B116AB94656F1552):
  * `GET /v2/data/<contract>.json` - registry-driven read route. Only contracts marked `client:true` are served,
    so `library-index` and `unwatched-pool` (producer-only, 0.6 MB / 2085 rows) are 404 by construction.
  * strict CSP + `nosniff` + `no-referrer` on `/v2/` responses **only** - the legacy pages are built from inline
    `<style>`/`<script>` and would break under it. They are untouched until the P5 cutover.
  * realpath containment check on static serving (the path join never rejected `..`; the extension allow-list made
    that harmless, but defence in depth is cheaper than depending on that staying true).
  * content-hashed assets get a 1-year immutable cache; `index.html` and contracts are `no-store`.

**Verified by effect**
* `/v2/` renders on desktop (1280x800: 4-col grid, full-width hero) and phone (375x812: single column, no
  horizontal overflow, 67x44 tap target) with **zero console messages** - no CSP violations, no Svelte errors.
* Reroll end-to-end from the page: `idx` 4 -> 5, pick changed *The Edge of Heaven* -> *American Graffiti*
  (seeded by *Superbad*), new backdrop cached, contract re-validated. No download triggered - the verb only
  re-pins a local index.
* Route allow-list: `library-index`/`unwatched-pool`/`registry`/unknown names, `..`, and URL-encoded `..` all 404;
  `services`/`smart`/`passport` 200. CSP present on `/v2/` and absent on `/`.
* Built page contains 0 inline scripts, 0 inline `style=` attributes, 0 external-host references, and the live
  20-hex `/act` nonce is still injected at serve time.
* `freshness.test.mjs` 16/16 PASS. Validator 20/20 valid. leak-grep PASS on the release dir before the flip.
* Legacy dashboard still 200 with 19 cards / 1 hero after both server restarts (0.63 s and 0.60 s of downtime).

**Fixed during P1 (found by verifying instead of assuming)**
* The bundle's CSS was served as `application/octet-stream` because `SimpleHTTPRequestHandler.extensions_map`
  holds only the compressed-file types - real MIME resolution lives in `guess_type()`. My own `nosniff` header then
  correctly refused to apply it, so the page rendered **completely unstyled** while HTTP status, contract fetches,
  console output and the DOM tree all looked perfect. Now uses `self.guess_type(fp)` + explicit charset.

## [P0] 2026-07-29 - Contract extraction (no user-visible change)

**Added**
* `contracts\registry.json` - 20 contracts with version / producer / cadence / SLO / consumers / client-facing flag.
  Documents one deliberate deviation from the gameplan seed table: the seed's single `pulse (svc/disk/queue/vpn)`
  row is split into one contract **per card** (`services`, `storage`, `pipeline`, `hnr`, `library-stats`,
  `plex-now`, `calendar`, `activity`, `health`, `security`, `smart`) so each card gets its own SLO and its own
  error state, per architecture rule "each card reads a named JSON contract". Nothing was dropped.
* 20 JSON Schemas (draft-07 subset), authored against the **real** payload shapes after introspecting every
  producer output - not against assumptions. (Reality corrected three guesses: `genres` is an array in
  `library-index` and `unwatched-pool`, and `taste-graph` carries two personas, `michael` and `kids`.)
* `producers\brain_contracts.py` - the `{_meta, data}` envelope, `_meta` stamping from the registry, atomic
  tmp+replace writes, BOM-tolerant reads.
* `producers\emit_ops.py` - 13 ops contracts from the dict `gen-dashboard.py` already gathers. Each contract is
  written in its own try/except; results land in `data\_emit-status.json`.
* `producers\wrap_files.py` - 7 wrapped contracts from existing producer JSON, `generated_at` = source mtime.
  Skips rewriting when the source is unchanged *and* the contract already carries the current registry version.
* `validate-contracts.py` - schema + envelope + freshness gate. Dependency-free (jsonschema is not installed and
  P0 deliberately adds nothing to the production python env). Exit 0 = valid+fresh, 2 = valid but stale,
  1 = hard failure. Rejects unenforced schema keywords; reports registry orphans.
* `leak-grep.ps1` - harvests 19 real secret values (wg\*.key, *.pass, *.url, act/cmd secrets, ntfy topic, Plex
  registry token, Trakt OAuth) and greps a tree for them. Exact hit = hard fail; generic patterns = warnings.
  Discards any harvested value under 8 chars so a short/empty secret file cannot match every file.

**Changed**
* `wg\dashboard\gen-dashboard.py` - **+11 lines only**, after the page's atomic write, fully guarded: hands the
  gathered dict to `emit_ops.emit()`. Backup at `gen-dashboard.py.bak-preP0`
  (sha256 40776E80D6DEB8E29BF5C7DB0DAFD080097B908AA3B2CD5B7C07D98BF16438EE).

**Verified by effect**
* Validator: 20/20 contracts present, envelope-correct and schema-valid. Exit 2 - honestly red on the one
  contract that really is stale (`unwatched-pool`, 13.3 d against an 8 d SLO) and `SNAPSHOT` on the two producers
  that have no scheduled task at all (`upgrades` 26.1 d, `passport` 26.0 d).
* Structural parity of the live page: 19 cards / 1 hero / 19 card headings before and after, heading list
  identical with digits normalized. The only markup delta was 3 CSS classes = exactly one `qrow` row
  (12 -> 11), explained by the pipeline contract's `active`=3 (+8 capped upgrade rows) vs 4 active before: data,
  not structure.
* `GET http://127.0.0.1:8500/` -> 200, all card markers present, live 20-hex `/act` nonce still injected at serve
  time (placeholder present on disk, absent in the response - the action plumbing is intact).
* Contract data is **not** reachable over HTTP: `/services.json` -> 404 and `/../brain/data/services.json` -> 404
  against the existing SEC-3 serve allow-list. (P1 will add a narrow, registry-driven read route.)
* `leak-grep.ps1` -> PASS, 0 exact hits over 47 files.
* Regen cost: 4.60 / 4.61 s patched vs 4.68 / 4.71 s pre-patch - emission is below measurement noise.
