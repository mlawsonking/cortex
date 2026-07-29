# Changelog - Cortex brain app

Semver on the app; each contract is versioned independently in `contracts\registry.json`.

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
