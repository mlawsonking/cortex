#!/usr/bin/env python3
# compression_ledger.py - I2 Compression Ledger: what has the x265 policy actually SAVED, and what would
# converting the x264 stragglers reclaim - ranked by size x low-rewatch-odds (ratings + watched flags from
# library-index; the I1 rhythm signal can sharpen the odds in a later pass).
#
# PROPOSAL-ONLY BY CONSTRUCTION: this emits numbers. The "re-grab compact" verb the gameplan sketches for the
# card does NOT exist server-side, and per the ground rules any new verb needs its own mini security review and
# Michael's approval BEFORE wiring - so the card renders the ledger with no buttons until that happens.
#
# Standalone producer, weekly task "Compression Ledger". HONEST EXIT: failure -> exit 1, write nothing.
import json, os, sys, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
# House estimate (same factor codec-advisor.ps1 uses): an x265 encode lands at ~55% of the x264 size for
# equivalent quality. saved = x264_equiv - actual; reclaimable = actual - est_hevc.
HEVC_FACTOR = 0.55


def key(n):
    return open(os.path.join(WG, n)).read().strip()


def codec_class(mi):
    c = (mi or "").lower()
    if any(x in c for x in ("265", "hevc")):
        return "hevc"
    if any(x in c for x in ("264", "avc")):
        return "avc"
    return "other"


def rewatch_weight(rating, watched):
    """Low-rewatch-odds weighting for the reclaim ranking. Judgements, stated plainly:
    a 9/10 film will be rewatched (don't churn it); an unwatched unrated file is pure shelf-weight."""
    if rating is not None and rating >= 9:
        return 0.15
    if rating is not None and rating >= 7:
        return 0.4
    if rating is not None:
        return 0.8          # watched and judged mediocre
    return 0.7 if watched else 1.0


def main():
    rk = key("radarr.key")
    movies = json.load(urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:7878/api/v3/movie", headers={"X-Api-Key": rk}), timeout=120))

    # rating/watched by radarrId from the library index (its producer is healthy/daily)
    idx = {}
    li = bc.read_json(os.path.join(WG, "audit", "library-index.json")) or []
    for r in li:
        if r.get("radarrId") is not None:
            idx[r["radarrId"]] = r

    buckets = {k: {"count": 0, "bytes": 0} for k in ("hevc", "avc", "other")}
    reclaim = []
    for m in movies:
        mf = m.get("movieFile") or {}
        if not m.get("hasFile") or not mf:
            continue
        size = mf.get("size") or m.get("sizeOnDisk") or 0
        cls = codec_class((mf.get("mediaInfo") or {}).get("videoCodec"))
        buckets[cls]["count"] += 1
        buckets[cls]["bytes"] += size
        if cls == "avc" and size > 2e9:            # tiny files are not worth churn
            info = idx.get(m.get("id"), {})
            rating = info.get("rating")
            watched = bool(info.get("watched"))
            save = size * (1 - HEVC_FACTOR)
            reclaim.append({
                "title": m.get("title", "?"), "year": m.get("year"), "radarrId": m.get("id"),
                "gb": round(size / 1e9, 2), "save_gb": round(save / 1e9, 2),
                "rating": rating, "watched": watched,
                "score": round(save / 1e9 * rewatch_weight(rating, watched), 2),
            })

    reclaim.sort(key=lambda r: -r["score"])
    hevc = buckets["hevc"]
    saved = hevc["bytes"] / HEVC_FACTOR - hevc["bytes"]

    data = {
        "hevc_factor": HEVC_FACTOR,
        "hevc": {"count": hevc["count"], "gb": round(hevc["bytes"] / 1e9, 1)},
        "avc": {"count": buckets["avc"]["count"], "gb": round(buckets["avc"]["bytes"] / 1e9, 1)},
        "other": {"count": buckets["other"]["count"], "gb": round(buckets["other"]["bytes"] / 1e9, 1)},
        "saved_gb": round(saved / 1e9, 1),
        "reclaim_candidates": len(reclaim),
        "reclaim_potential_gb": round(sum(r["save_gb"] for r in reclaim), 1),
        "reclaim": reclaim[:20],
    }
    path = bc.write_contract("ledger", data)
    print("ledger written: %s (hevc %d files, saved ~%.0f GB; %d reclaim candidates worth ~%.0f GB)"
          % (path, hevc["count"], saved / 1e9, len(reclaim), data["reclaim_potential_gb"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
