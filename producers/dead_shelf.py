#!/usr/bin/env python3
# dead_shelf.py - I3 Dead Shelf: the curation-debt report. Films that were deliberately curated into the library
# and then never played, never rated, aging on the shelf. "added > 60d, never played, not rated" made visible.
#
# The pool itself is produced upstream by wg\audit\get-unwatched-pool.py (task "Unwatched Pool"), which already
# encodes the membership rules: never-watched, never-rated, year >= 1987 (the house year floor). This producer
# does exactly one job on top of that: AGE it. Anything younger than 60 days is "settling" - not dead yet, just
# recently added - and is counted but never called debt.
#
# HONEST EXIT (guardrail 5 - never a plausible-looking lie):
#   * pool file missing / unparseable / not a list / fewer than MIN_POOL entries -> print CANNOT TELL, exit 2,
#     write NOTHING. The previous contract then ages into a STALE badge, which is the truth.
#   * any other failure -> exit 1, write nothing.
#   * an addedAt we cannot trust (null, non-positive, in the future, or predating the film's own release year -
#     e.g. a 2023 film stamped as added in 2004) is NOT guessed at. It goes to unknown_age, is reported, and is
#     excluded from every bucket and from the oldest list.
#
# SIZES: deliberately absent. The optional enrichment would be GB-per-bucket joined from library-index by tmdb,
# but library-index rows carry no size/bytes field at all (title, year, tmdb, radarrId, genres, runtime, hasFile,
# res, rating, watched), so there is nothing to join. Rather than estimate from resolution, this emits no sizes.
# The schema leaves total_gb/gb as OPTIONAL so a future index that really does carry sizes needs no schema edit.
#
# Standalone producer, daily task "Dead Shelf" 06:50.
import json, os, sys, time, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
POOL = os.path.join(WG, "audit", "unwatched-pool.json")
INDEX = os.path.join(WG, "brain", "data", "library-index.json")

MIN_POOL = 50            # below this the pool is a broken refresh, not a small library - refuse to report
SETTLING_DAYS = 60       # younger than this is not debt yet
OLDEST_N = 15
SIZE_KEYS = ("gb", "size_gb", "sizeGb", "bytes", "size", "sizeOnDisk")


def age_days(added, year, now):
    """Whole days on the shelf, or None when the timestamp cannot be trusted."""
    if not isinstance(added, (int, float)) or isinstance(added, bool) or added <= 0:
        return None
    if added > now + 86400:                       # stamped in the future
        return None
    try:
        added_year = datetime.datetime.fromtimestamp(added).year
    except Exception:
        return None
    if isinstance(year, int) and added_year < year - 1:   # added before the film existed
        return None
    return int((now - added) // 86400)


def size_index():
    """GB by tmdb id from library-index, but ONLY if the join is obviously clean. Returns {} otherwise."""
    env = bc.read_json(INDEX)
    rows = env.get("data") if isinstance(env, dict) else env
    if not isinstance(rows, list) or not rows:
        return {}
    key = None
    for k in SIZE_KEYS:
        if sum(1 for r in rows if isinstance(r, dict) and isinstance(r.get(k), (int, float))) > len(rows) * 0.9:
            key = k
            break
    if key is None:
        return {}                                  # no size field -> emit no sizes, do not estimate
    div = 1e9 if key in ("bytes", "size", "sizeOnDisk") else 1.0
    out = {}
    for r in rows:
        t = r.get("tmdb")
        v = r.get(key)
        if isinstance(t, int) and isinstance(v, (int, float)) and v > 0:
            out[t] = v / div
    return out


def main():
    if not os.path.isfile(POOL):
        print("CANNOT TELL: no unwatched pool at %s - the 'Unwatched Pool' producer has never run here."
              " Writing nothing." % POOL)
        return 2
    pool = bc.read_json(POOL)
    if not isinstance(pool, list):
        print("CANNOT TELL: %s did not parse as a list of pool entries. Writing nothing." % POOL)
        return 2
    if len(pool) < MIN_POOL:
        print("CANNOT TELL: pool has %d entries (< %d) - that reads as a broken refresh, not a small shelf."
              " Writing nothing." % (len(pool), MIN_POOL))
        return 2

    now = time.time()
    sizes = size_index()
    settling = unknown = 0
    buckets = {"d60_180": [], "d180_365": [], "over_365": []}
    dead = []

    for m in pool:
        if not isinstance(m, dict):
            unknown += 1
            continue
        days = age_days(m.get("addedAt"), m.get("year"), now)
        if days is None:
            unknown += 1
            continue
        if days < SETTLING_DAYS:
            settling += 1
            continue
        name = "d60_180" if days < 180 else ("d180_365" if days < 365 else "over_365")
        row = {
            "title": m.get("title") or "?",
            "year": m.get("year") if isinstance(m.get("year"), int) else None,
            "days": days,
            "genres": [g for g in (m.get("genres") or []) if isinstance(g, str)][:3],
            "tmdb": m.get("tmdb") if isinstance(m.get("tmdb"), int) else None,
            "ratingKey": str(m.get("ratingKey")) if m.get("ratingKey") is not None else None,
        }
        gb = sizes.get(row["tmdb"])
        if gb is not None:
            row["gb"] = round(gb, 2)
        buckets[name].append(row)
        dead.append(row)

    dead.sort(key=lambda r: -r["days"])
    total = len(pool)

    out_buckets = {}
    for name, rows in buckets.items():
        b = {"count": len(rows)}
        if sizes:
            known = [r["gb"] for r in rows if "gb" in r]
            if known:
                b["total_gb"] = round(sum(known), 1)
        out_buckets[name] = b

    data = {
        "pool_total": total,
        "settling": settling,
        "unknown_age": unknown,
        "buckets": out_buckets,
        "dead_total": len(dead),
        "dead_pct": round(100.0 * len(dead) / total, 1) if total else 0.0,
        "oldest": dead[:OLDEST_N],
    }
    path = bc.write_contract("dead-shelf", data)
    print("dead-shelf written: %s (%d dead of %d pool = %.1f%%; 60-180d %d / 180-365d %d / >365d %d;"
          " %d settling, %d undateable; sizes: %s)"
          % (path, data["dead_total"], total, data["dead_pct"], out_buckets["d60_180"]["count"],
             out_buckets["d180_365"]["count"], out_buckets["over_365"]["count"], settling, unknown,
             "joined from library-index" if sizes else "SKIPPED - library-index carries no size field"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
