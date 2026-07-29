# Cortex - the media-server brain app

**Start here if you are a new session.** The spec is `C:\Users\bobdo\wg\GAMEPLAN-BRAIN-APP.md` (architecture,
phases P0-P6, insight engines I1-I10, governance, the 9 guardrails). The contract registry
(`contracts\registry.json`) is the source of truth for what data exists. If this README and the gameplan ever
disagree, **the gameplan wins**.

This is a **foundation swap**, not a rewrite: the intelligence already existed as ~20 JSON producers. What was
missing was a contract layer (validated, versioned, honestly dated) and a component renderer to replace 51 KB of
string-concatenated HTML in `wg\dashboard\gen-dashboard.py`.

## Layout

```
wg\brain\
  contracts\registry.json         THE registry: version, producer, cadence, SLO, consumers, client-facing?
  contracts\<name>.schema.json    one JSON Schema per contract (20 of them)
  producers\brain_contracts.py    envelope + _meta stamping + atomic writes + registry loader
  producers\emit_ops.py           gen-dashboard's gathered dict  -> 13 ops contracts
  producers\wrap_files.py         existing producer JSON files    -> 7 wrapped contracts
  validate-contracts.py           schema + envelope + freshness gate, honest exit codes
  leak-grep.ps1                   secret-leak gate (harvests real secrets, greps a tree)
  data\                           runtime output (git-ignored, regenerated every ~120s)
```

## The envelope

Every file in `data\` has exactly this shape:

```json
{"_meta": {"contract","version","generated_at","producer","slo_seconds","emitted_at","source"}, "data": ...}
```

## Honesty rules (guardrail 5 - these are the whole point)

* `generated_at` is when the **data** was produced. For a wrapped or cached producer that is the **source file's
  mtime**, never the copy time. Copying stale data does not make it fresh.
* `slo_seconds: null` means *no schedule exists for this producer* (e.g. `upgrades`, `passport` - there is no
  scheduled task). Render the age, never a STALE badge, never an implied freshness. The registry calls this
  status `SNAPSHOT`.
* A producer whose source is missing or unparseable writes **nothing**, so the previous contract ages out and
  reads STALE - which is true. Writing an empty-but-freshly-stamped payload would be exactly the plausible-looking
  lie the guardrails forbid.
* `validate-contracts.py` rejects any schema keyword it does not actually enforce. A validator that silently skips
  half a schema is worse than none: it reports green while checking nothing.

## Everyday commands

```
python validate-contracts.py                 # table; exit 0 = all valid+fresh, 2 = valid but stale, 1 = hard fail
python validate-contracts.py --json          # machine-readable (verify-brain.ps1 consumes this in P6)
python validate-contracts.py --check-sources # also cross-check registry.source vs wrap_files.SOURCES
python producers\wrap_files.py --force       # re-wrap the file-based contracts now
powershell -NoProfile -ExecutionPolicy Bypass -File leak-grep.ps1   # must PASS before any release goes live
```

## How contracts get written

There is **no new service, port, listener or scheduled task.** `wg\dashboard\gen-dashboard.py` already gathers all
ops data every ~120 s under `dashboard-server.py`; its final 11 lines (added in P0) hand that dict to
`emit_ops.emit()`, which writes the ops contracts and then refreshes the wrapped ones. The hook sits **after** the
page's atomic write and is wrapped in `try/except`, so a contract failure can never affect the served dashboard.
Measured cost: below noise (~0.1 s of a ~4.6 s regen).

Failures are recorded honestly in `data\_emit-status.json` (`written` / `unchanged_skipped` / `failed`) because a
hook cannot exit with a status code.

## Rollback

* **P0 only:** `copy wg\dashboard\gen-dashboard.py.bak-preP0 wg\dashboard\gen-dashboard.py` and delete `wg\brain`.
  Nothing else is touched; the old dashboard never depended on any of this.
