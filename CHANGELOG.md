# Changelog - Cortex brain app

Semver on the app; each contract is versioned independently in `contracts\registry.json`.

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
