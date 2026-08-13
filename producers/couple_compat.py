#!/usr/bin/env python3
# couple_compat.py - I5 Couple Compatibility: his-taste x her-lanes, venn'd over the owned-but-unwatched pool.
# The question this answers is "what is already ON THE SHELF that BOTH of them would sit down for?" - i.e. date
# night candidates, not new downloads. Nothing here grabs, monitors or moves anything; it ranks what we own.
#
# THE ASYMMETRY IS DELIBERATE AND STATED, NOT PAPERED OVER: the household shares one Plex account, so history
# gives us a 'michael' persona and a 'kids' persona and NOTHING for his wife. Her side is therefore RULE-DEFINED
# in ..\her-lanes.json (romance / rom-com / Neeson-thrillers), hand-written and human-editable. Inventing a
# learned persona for someone with no separate signal would be exactly the plausible-looking lie this rebuild
# exists to kill. His side IS learned - the michael persona's genre play-counts, normalized 0..1.
#
# Standalone producer, weekly task "Couple Compat" (Sun 06:45). HONEST EXIT:
#   0 = contract written
#   2 = CANNOT TELL (pool missing/too thin, lanes config unusable, or no usable his-taste weights) - writes
#       NOTHING, so the previous contract ages into a STALE badge, which is the truth
#   1 = unexpected failure - also writes nothing
import json, os, sys, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
AUDIT = os.path.join(WG, "audit")
POOL = os.path.join(AUDIT, "unwatched-pool.json")
TASTE_GRAPH = os.path.join(AUDIT, "taste-graph.json")
TRAKT = os.path.join(AUDIT, "trakt-ratings.json")
LANES = os.path.join(bc.BRAIN, "her-lanes.json")

MIN_POOL = 50           # below this the pool is broken, not thin - refuse rather than rank noise
TOP_PER_LANE = 8
TOP_DATE_NIGHT = 10
MIN_GENRES_FOR_TASTE = 3


def cannot(why):
    print("CANNOT TELL: %s" % why)
    return 2


# ---------------------------------------------------------------- his taste

def taste_from_graph():
    """Preferred path: the michael persona's genre play-counts from taste-graph.json, normalized to 0..1 by his
    single most-played genre. Returns {genre_lower: weight} or None if the shape has nothing usable."""
    tg = bc.read_json(TASTE_GRAPH)
    if not isinstance(tg, dict):
        return None
    personas = tg.get("personas")
    if not isinstance(personas, dict):
        return None
    m = personas.get("michael")
    if not isinstance(m, dict):
        return None
    counts = {}
    for g in (m.get("topGenres") or []):
        if not isinstance(g, dict):
            continue
        name, n = g.get("genre"), g.get("count")
        if isinstance(name, str) and name.strip() and isinstance(n, (int, float)) and n > 0:
            counts[name.strip().lower()] = float(n)
    if len(counts) < MIN_GENRES_FOR_TASTE:
        return None
    top = max(counts.values())
    return {k: round(v / top, 4) for k, v in counts.items()}


def taste_from_ratings():
    """Fallback path only: mean Trakt rating per genre, genres joined in from Radarr by tmdbId, min-max
    normalized to 0..1 (raw means bunch up around 7-9, so a plain divide-by-max would flatten the signal)."""
    ratings = bc.read_json(TRAKT)
    if not isinstance(ratings, list) or not ratings:
        return None
    try:
        key = open(os.path.join(WG, "radarr.key")).read().strip()
        req = urllib.request.Request("http://127.0.0.1:7878/api/v3/movie", headers={"X-Api-Key": key})
        movies = json.load(urllib.request.urlopen(req, timeout=120))
    except Exception as e:
        print("note: Radarr genre join failed (%s: %s)" % (type(e).__name__, e))
        return None
    genres_by_tmdb = {}
    for mv in movies:
        t = mv.get("tmdbId")
        if t:
            genres_by_tmdb[int(t)] = [g for g in (mv.get("genres") or []) if isinstance(g, str)]

    acc = collections.defaultdict(list)
    for r in ratings:
        if not isinstance(r, dict) or r.get("type") not in (None, "movie"):
            continue
        score = r.get("rating")
        tmdb = (((r.get("movie") or {}).get("ids") or {}).get("tmdb"))
        if not isinstance(score, (int, float)) or not tmdb:
            continue
        for g in genres_by_tmdb.get(int(tmdb), []):
            acc[g.strip().lower()].append(float(score))

    means = {g: sum(v) / len(v) for g, v in acc.items() if len(v) >= 3}
    if len(means) < MIN_GENRES_FOR_TASTE:
        return None
    lo, hi = min(means.values()), max(means.values())
    if hi - lo < 1e-9:
        return {g: 1.0 for g in means}
    return {g: round((v - lo) / (hi - lo), 4) for g, v in means.items()}


# ---------------------------------------------------------------- her lanes

def load_lanes():
    cfg = bc.read_json(LANES)
    if not isinstance(cfg, dict):
        return None
    out = []
    for lane in (cfg.get("lanes") or []):
        if not isinstance(lane, dict):
            continue
        k, label = lane.get("key"), lane.get("label")
        if not isinstance(k, str) or not k:
            continue
        def lower(name):
            return set(x.strip().lower() for x in (lane.get(name) or []) if isinstance(x, str) and x.strip())
        cond = {"key": k, "label": label if isinstance(label, str) and label else k,
                "genres_all": lower("genres_all"), "genres_any": lower("genres_any"),
                "actors_any": lower("actors_any")}
        if not (cond["genres_all"] or cond["genres_any"] or cond["actors_any"]):
            continue                       # a lane with no conditions would match the entire library
        out.append(cond)
    return out or None


def lane_matches(lane, genres, actors):
    """Every NON-EMPTY condition must hold. An empty list is 'no opinion', not 'match nothing'."""
    if lane["genres_all"] and not lane["genres_all"].issubset(genres):
        return False
    if lane["genres_any"] and not (lane["genres_any"] & genres):
        return False
    if lane["actors_any"] and not (lane["actors_any"] & actors):
        return False
    return True


# ---------------------------------------------------------------- main

def main():
    pool = bc.read_json(POOL)
    if not isinstance(pool, list):
        return cannot("unwatched pool unreadable at %s (run its producer first)" % POOL)
    if len(pool) < MIN_POOL:
        return cannot("unwatched pool has only %d entries (need %d) - that is a broken pool, not a thin one"
                      % (len(pool), MIN_POOL))

    lanes = load_lanes()
    if lanes is None:
        return cannot("her-lanes.json has no usable lanes at %s" % LANES)

    weights = taste_from_graph()
    source = "taste-graph"
    if weights is None:
        weights = taste_from_ratings()
        source = "ratings+radarr"
    if weights is None:
        return cannot("no usable his-taste genre weights from taste-graph.json or trakt-ratings.json+Radarr")

    per_lane = {l["key"]: [] for l in lanes}
    matched_any = 0
    scored = []
    for it in pool:
        if not isinstance(it, dict):
            continue
        raw_genres = [g for g in (it.get("genres") or []) if isinstance(g, str)]
        genres = set(g.strip().lower() for g in raw_genres)
        actors = set(a.strip().lower() for a in (it.get("actors") or []) if isinstance(a, str))

        hits = [l for l in lanes if lane_matches(l, genres, actors)]
        if not hits:
            continue                       # counted in pool_total, kept off every shelf
        matched_any += 1

        vals = [weights.get(g, 0.0) for g in genres]
        his = round(sum(vals) / len(vals), 4) if vals else 0.0

        rec = {"title": it.get("title") or "?", "year": it.get("year"), "tmdb": it.get("tmdb"),
               "ratingKey": str(it.get("ratingKey")) if it.get("ratingKey") is not None else None,
               "genres": raw_genres[:3], "his_score": his,
               "rating": it.get("rating"), "lanes": [l["key"] for l in hits]}
        scored.append(rec)
        for l in hits:
            per_lane[l["key"]].append(rec)

    def rank(recs):
        # his_score first; community rating breaks ties, then title so the shelf is stable run to run
        return sorted(recs, key=lambda r: (-r["his_score"], -(r["rating"] or 0), r["title"]))

    lanes_out = []
    for l in lanes:
        top = rank(per_lane[l["key"]])[:TOP_PER_LANE]
        lanes_out.append({
            "key": l["key"], "label": l["label"], "matches": len(per_lane[l["key"]]),
            "top": [{"title": r["title"], "year": r["year"], "tmdb": r["tmdb"], "ratingKey": r["ratingKey"],
                     "genres": r["genres"], "his_score": round(r["his_score"], 2)} for r in top],
        })

    date_night = [{"title": r["title"], "year": r["year"], "tmdb": r["tmdb"], "ratingKey": r["ratingKey"],
                   "lanes": r["lanes"], "his_score": round(r["his_score"], 2)}
                  for r in rank(scored)[:TOP_DATE_NIGHT]]

    data = {
        "pool_total": len(pool),
        "matched_any": matched_any,
        "lanes": lanes_out,
        "date_night": date_night,
        "taste_source": source,
    }
    path = bc.write_contract("couple-compat", data)
    print("couple-compat written: %s (pool %d, %d on a shelf, taste from %s)"
          % (path, len(pool), matched_any, source))
    print("  lanes: %s" % " | ".join("%s=%d" % (l["key"], l["matches"]) for l in lanes_out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
