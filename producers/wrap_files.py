# wrap_files.py - wrap the standalone producers' existing JSON outputs as versioned contracts.
# P0 of the Cortex brain app. Pure stdlib, pure ASCII source.
#
# The originals are NEVER touched or moved: the *arr-facing producers keep writing exactly where they always did
# (wg\audit\*.json, wg\dashboard\*.json) and the old dashboard keeps reading them. We add a contract-shaped copy
# under wg\brain\data\ whose generated_at is the SOURCE FILE's mtime - the data's real age, not the copy's age.
#
# TWO HONESTY RULES:
#   1. Unchanged source  -> skip the rewrite entirely (idempotent; keeps a 0.6 MB index off the disk every 120s).
#   2. Missing/unparseable source -> write NOTHING and report the failure. The previously-written contract then
#      ages out and shows STALE, which is true. Overwriting it with an empty-but-freshly-stamped payload would be
#      exactly the "plausible-looking lie" the guardrails forbid.
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"

# contract name -> source file, relative to wg\. Kept in sync with contracts\registry.json ("source" field);
# validate-contracts.py --check-sources proves the two agree.
SOURCES = {
    "recs": r"audit\personal-recs.json",
    "oracle": r"dashboard\oracle.json",
    "library-index": r"audit\library-index.json",
    "taste-graph": r"audit\taste-graph.json",
    "unwatched-pool": r"audit\unwatched-pool.json",
    "upgrades": r"dashboard\upgrade-proposals.json",
    "passport": r"dashboard\passport.json",
}


def _current_version(name):
    cur = bc.read_json(os.path.join(bc.DATA, name + ".json"))
    try:
        return cur["_meta"].get("version")
    except Exception:
        return None


def wrap_one(name, force=False):
    """Returns (True, None) on write, (False, None) on a legitimate skip, (False, reason) on failure."""
    src = os.path.join(WG, SOURCES[name])
    st = bc.mtime(src)
    if st is None:
        return False, "source missing: %s" % SOURCES[name]
    # Skip only when the source is unchanged AND the already-written contract carries the current registry
    # version. Without the version test, a registry version bump would never reach an unchanged source's
    # contract and validate-contracts would report a permanent version mismatch.
    stale_version = _current_version(name) != bc.entry(name)["version"]
    if not force and not stale_version and bc.contract_source_mtime(name) == st:
        return False, None
    data = bc.read_json(src)
    if data is None:
        return False, "source unparseable: %s" % SOURCES[name]
    bc.write_wrapped(name, data, src)
    return True, None


def wrap_all(force=False):
    """Returns (written, failed, skipped). 'skipped' is reported separately from 'written' so a status reader can
    never mistake 'source unchanged, nothing to do' for 'this contract failed to emit'."""
    ok, failed, skipped = [], [], []
    for name in SOURCES:
        try:
            wrote, reason = wrap_one(name, force=force)
            if wrote:
                ok.append(name)
            elif reason:
                failed.append({"contract": name, "error": reason})
            else:
                skipped.append(name)
        except Exception as e:
            failed.append({"contract": name, "error": "%s: %s" % (type(e).__name__, e)})
    return ok, failed, skipped


if __name__ == "__main__":
    force = "--force" in sys.argv
    o, f, s = wrap_all(force=force)
    print("wrapped: %s" % (", ".join(sorted(o)) or "(none)"))
    if s:
        print("unchanged (skipped): %s" % ", ".join(sorted(s)))
    for x in f:
        print("  FAIL %s: %s" % (x["contract"], x["error"]))
    sys.exit(1 if f else 0)
