# rate_queue.py - "rate what you watched" (wg\GAMEPLAN-TASTE-LOOP-2026-11.md s4) -> contract rate-queue.
#
# POOL: titles played on michael's Plex account (Movies viewCount > 0 or abandoned part-way; series with >= 3
# watched episodes) that carry a TMDB id and are not yet answered (effectively rated, not-me, bailed, or skipped in
# the last 30 days) and not hero-drop (curated for Nathaniel).
#
# THE HOUSEHOLD PROBLEM (measured 2026-11-02): 5,469 of 5,476 plays are on account 1 - the kids and his wife watch
# as michael. A play is therefore never taste; it only nominates a title for HIM to rate. Two filters:
#   1. content (hard): G / TV-Y / TV-Y7 / TV-G, or Family / Kids / Children, or Animation while his ratings keep that
#      lane closed (taste_core's rule), on Plex OR TMDB genres -> hidden, counted, listed under "show them".
#   2. play context (soft, learned): a naive-Bayes "was it michael?" from each play's DEVICE and HOUR, trained on
#      content-labelled plays (kids titles = household, titles he rated = him) plus every "not me" he taps. The
#      living-room Roku is 92% kids titles; 21:00-23:00 is his. A title keeps its most-michael play. Below
#      HIDE_P it is hidden like (1); below DOUBT_P it is asked with a "maybe household" reason.
#   Titles matching her-lanes.json (romance / rom-com) that taste_core scores low get "maybe hers" and a discount -
#   still askable: if he watched it with her, his rating is real signal.
#
# LEVERAGE = 0.40 influence + 0.25 uncertainty + 0.20 freshness + 0.15 coverage (each 0-1), times the context
# factor. influence = how many current candidates (Streaming Best, Missed Gems, the unwatched pool - TMDB cache
# only) are similar enough that this rating moves them; uncertainty = the guess near the love/meh line or a title far
# from every seed; freshness = exp(-days since played / 45); coverage = the first film of a director he has not
# rated, or a thin genre. Every item carries 1-3 reason strings built from those terms - the UI never invents prose.
# The "guess" (taste_eval's calibration of match -> rating) is hidden by the UI until he has rated.
#
# --quick (after every rating verb, single-flight, cache-only, < 1 s): re-filter the CURRENT contract against the
# ledger so a reload never shows an answered title, refresh the backlog counters. The nightly full run rescores.
import argparse, collections, datetime, json, math, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_contracts as bc
import taste_core as tc
import taste_ledger as tl
import taste_eval as te

MAX_ITEMS = 60
MAX_HOUSEHOLD = 30
SESSION_CAP = 10
HIGH_LEVERAGE = 0.5
SIM_THRESH = 0.06            # raw similarity that counts as "this rating moves that candidate" (calibrated T3)
FRESH_DAYS = 45.0
HIDE_P, DOUBT_P = 0.20, 0.45
SHOW_MIN_EPS = 3
BAIL_MIN_S, BAIL_MAX_FRAC, BAIL_IDLE_D = 15 * 60, 0.40, 14
SKIP_DAYS = 30
HH_RATINGS = {"G", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G"}
HERO_TAG = "hero-drop"
LOCK = os.path.join(bc.DATA, ".rate-queue.lock")
STASH_NAME = ".rate-queue-stash.json"   # rows --quick removed (an undo restores them); resolved per call


def log(msg):
    print(msg, flush=True)


def plex_json(path, token, timeout=180):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(tc.PLEX + path + sep + "X-Plex-Token=" + token, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))["MediaContainer"]


def tmdb_guid(m):
    for g in m.get("Guid") or []:
        gid = g.get("id", "")
        if gid.startswith("tmdb://") and gid[7:].isdigit():
            return int(gid[7:])
    return None


def tags(m, name):
    return [x.get("tag") for x in m.get(name) or [] if x.get("tag")]


def logit(p):
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def household_content(genres, content_rating, animation_ok):
    g = set(genres)
    if content_rating in HH_RATINGS:
        return "rated %s" % content_rating
    if g & tc.KIDS:
        return "kids/family title"
    if "Animation" in g and not animation_ok:
        return "animation (your ratings keep that lane closed)"
    return None


class Context(object):
    """Naive Bayes P(michael | device, hour) from content-labelled plays. Laplace-smoothed per device / hour."""

    def __init__(self, plays, labels, dev_names):
        self.dev, self.hour = collections.defaultdict(lambda: [1.0, 1.0]), collections.defaultdict(lambda: [1.0, 1.0])
        n_me = n_all = 0
        for p in plays:
            lab = labels.get(p["title_key"])
            if lab is None:
                continue
            self.dev[p["device"]][0 if lab else 1] += 1
            self.hour[p["hour"]][0 if lab else 1] += 1
            n_me += lab
            n_all += 1
        self.prior = (n_me + 1.0) / (n_all + 2.0)
        self.names = dev_names
        self.n = n_all

    def p(self, device, hour):
        lp = logit(self.prior)
        d, h = self.dev.get(device), self.hour.get(hour)
        x = lp
        if d:
            x += logit(d[0] / (d[0] + d[1])) - lp
        if h:
            x += logit(h[0] / (h[0] + h[1])) - lp
        return sigmoid(x)

    def explain(self, device, hour):
        d = self.dev.get(device)
        name = self.names.get(device) or "a shared device"
        share = int(round(100 * d[1] / (d[0] + d[1]))) if d else None
        return "played %s on %s%s" % ("in the morning" if 5 <= hour < 10 else ("in the afternoon" if 10 <= hour < 18 else
                                       ("in the evening" if 18 <= hour < 21 else "late")),
                                       name, (" (%d%% household there)" % share) if share is not None else "")


def answered(signals, eff_keys, now):
    done = set(eff_keys)
    for d in signals.get("household") or []:
        done.add(d["key"])
    for d in signals.get("bailed") or []:
        done.add(d["key"])
    for d in signals.get("skipped") or []:
        if d.get("until", 0) > now:
            done.add(d["key"])
    return done


def ledger_stats(events, now):
    void = tl.voided_ids(events)
    days = collections.Counter()
    r7 = r30 = 0
    for e in events:
        if e.get("src") != "dash" or e["id"] in void or e.get("kind") not in ("rating", "bailed", "notme"):
            continue
        t = tl.epoch(e.get("ts"))
        if now - t < 7 * 86400:
            r7 += 1
        if now - t < 30 * 86400:
            r30 += 1
        days[datetime.date.fromtimestamp(t)] += 1
    streak, d = 0, datetime.date.fromtimestamp(now)
    if d not in days:
        d -= datetime.timedelta(days=1)      # today not yet rated: the streak is still alive until midnight
    while d in days:
        streak += 1
        d -= datetime.timedelta(days=1)
    return r7, r30, streak


def raw_sim(cs, ss):
    ppl = 1.0 if (cs["directors"] & ss["directors"]) else (0.6 if len(cs["cast"] & ss["cast"]) else 0.0)
    return (0.70 * tc.jaccard(cs["keywords"], ss["keywords"]) + 0.30 * ppl) * (0.4 + 0.6 * tc.jaccard(cs["genres"], ss["genres"]))


def candidate_sets():
    """Feature sets of everything the pages could show next (cache only - no TMDB calls)."""
    want = set()
    for r in bc.read_json(os.path.join(bc.DATA, "unwatched-pool.json")).get("data") or []:
        if r.get("tmdb"):
            want.add(("movie", int(r["tmdb"])))
    sb = (bc.read_json(os.path.join(bc.DATA, "streaming-best.json")) or {}).get("data") or {}
    mg = (bc.read_json(os.path.join(bc.DATA, "missed-gems.json")) or {}).get("data") or {}
    for r in (sb.get("items") or []) + (mg.get("landed") or []) + (mg.get("gems") or []) + (mg.get("shows") or []):
        if r.get("tmdb_id"):
            want.add((r["type"], int(r["tmdb_id"])))
    out = []
    for kind, tid in want:
        f = bc.read_json(os.path.join(tc.CACHE, "%s-%d.json" % (kind, tid)))
        if isinstance(f, dict) and f.get("keywords") is not None:
            out.append(tc.feature_sets(f))
    return out


def write(data):
    bc.write_contract("rate-queue", data)


# ------------------------------------------------------------------------------------------------------- quick
def quick():
    env = bc.read_json(os.path.join(bc.DATA, "rate-queue.json"))
    if not isinstance(env, dict) or "data" not in env:
        log("quick: no rate-queue contract yet - nothing to refresh")
        return 0
    d = env["data"]
    now = time.time()
    events, _ = tl.read_events()
    eff, signals, _ = tl.fold(tl.load_base(), events)
    eff_keys = {tl.key_of(r.get("type") or "movie", (r.get("movie") or r.get("show"))["ids"]["tmdb"]) for r in eff}
    done = answered(signals, eff_keys, now)

    def k(r):
        return tl.key_of(r["type"], r["tmdb_id"])

    # Removed rows go to a sidecar stash so an UNDO can bring them back without waiting for the nightly rescore.
    stash = bc.read_json(os.path.join(bc.DATA, STASH_NAME)) or {}
    if stash.get("generated_at") != env["_meta"].get("generated_at"):
        stash = {"generated_at": env["_meta"].get("generated_at"), "rows": {}}
    before = len(d["items"])
    for lst in ("items", "household"):
        keep = []
        for r in d.get(lst) or []:
            if k(r) in done:
                stash["rows"][r["key"]] = [lst, r]
            else:
                keep.append(r)
        d[lst] = keep
    back = 0
    for key, (lst, r) in list(stash["rows"].items()):
        if k(r) not in done:
            d[lst].append(r)
            del stash["rows"][key]
            back += 1
    d["items"].sort(key=lambda r: -r["leverage"])
    tl.write_json(os.path.join(bc.DATA, STASH_NAME), stash)
    removed = before - len(d["items"])
    b = d["backlog"]
    b["total"] = max(0, b["total"] - removed)
    b["high_leverage"] = sum(1 for r in d["items"] if r["leverage"] >= HIGH_LEVERAGE) + \
        max(0, b.get("beyond_high", 0))
    b["rated_7d"], b["rated_30d"], b["streak_days"] = ledger_stats(events, now)
    d["refreshed_at"] = bc.iso(now)
    bc.write_contract("rate-queue", d, generated_at_ts=tl.epoch(env["_meta"].get("generated_at")) or None)
    log("quick: %d answered titles removed, %d restored by undo, %d left in view" % (max(0, removed), back, len(d["items"])))
    return 0


# -------------------------------------------------------------------------------------------------------- full
def full():
    now = time.time()
    token = tc.plex_token()
    events, _ = tl.read_events()
    eff, signals, _ = tl.fold(tl.load_base(), events)
    eff_keys = {tl.key_of(r.get("type") or "movie", (r.get("movie") or r.get("show"))["ids"]["tmdb"]) for r in eff}
    done = answered(signals, eff_keys, now)
    notme_keys = {d["key"] for d in signals.get("household") or []}

    taste = tc.Taste(log).build(tc.api_key("tmdb"))
    ev_state = bc.read_json(tl.P("eval")) or {}
    table = ev_state.get("calibration") or []

    # --- library: watched / abandoned movies, watched series ---
    movies = plex_json("/library/sections/1/all?type=1&includeGuids=1", token).get("Metadata") or []
    shows = plex_json("/library/sections/2/all?type=2&includeGuids=1", token).get("Metadata") or []
    titles = {}                 # title_key (movie:<tmdb> / tv:<tmdb>) -> candidate dict
    rk_to_key = {}
    for m in movies:
        tid = tmdb_guid(m)
        if not tid:
            continue
        k = "movie:%d" % tid
        rk_to_key[str(m["ratingKey"])] = k
        vc, off, dur = int(m.get("viewCount") or 0), int(m.get("viewOffset") or 0), int(m.get("duration") or 0)
        last = int(m.get("lastViewedAt") or 0)
        bailed = (vc == 0 and off >= BAIL_MIN_S * 1000 and dur and off / float(dur) < BAIL_MAX_FRAC
                  and last and now - last > BAIL_IDLE_D * 86400)
        if vc == 0 and not bailed:
            continue
        titles[k] = {"type": "movie", "tmdb": tid, "rk": str(m["ratingKey"]), "title": m.get("title") or "?",
                     "year": m.get("year"), "cr": m.get("contentRating"), "genres": tags(m, "Genre"),
                     "actors": tags(m, "Role"), "last": last, "completion": int(round(100.0 * off / dur)) if bailed else None,
                     "plex_rated": m.get("userRating") is not None}
    for s in shows:
        tid = tmdb_guid(s)
        if not tid:
            continue
        k = "tv:%d" % tid
        rk_to_key[str(s["ratingKey"])] = k
        if int(s.get("viewedLeafCount") or 0) < SHOW_MIN_EPS:
            continue
        titles[k] = {"type": "tv", "tmdb": tid, "rk": str(s["ratingKey"]), "title": s.get("title") or "?",
                     "year": s.get("year"), "cr": s.get("contentRating"), "genres": tags(s, "Genre"), "actors": [],
                     "last": int(s.get("lastViewedAt") or 0), "completion": None,
                     "eps": "%s of %s episodes" % (s.get("viewedLeafCount"), s.get("leafCount")),
                     "plex_rated": s.get("userRating") is not None}

    # --- hero-drop exclusion (curated for Nathaniel) ---
    hero = set()
    try:
        rtag = next((t["id"] for t in tc.arr_get(tc.RADARR, "radarr", "/tag") if t.get("label") == HERO_TAG), None)
        stag = next((t["id"] for t in tc.arr_get(tc.SONARR, "sonarr", "/tag") if t.get("label") == HERO_TAG), None)
        for m in tc.arr_get(tc.RADARR, "radarr", "/movie"):
            if rtag in (m.get("tags") or []) and m.get("tmdbId"):
                hero.add("movie:%d" % m["tmdbId"])
        for s in tc.arr_get(tc.SONARR, "sonarr", "/series"):
            if stag in (s.get("tags") or []) and s.get("tmdbId"):
                hero.add("tv:%d" % s["tmdbId"])
    except Exception as ex:
        taste.notes.append("hero-drop tags unreadable (%s) - not excluded" % type(ex).__name__)

    # --- play context model ---
    hist = plex_json("/status/sessions/history/all?sort=viewedAt:desc&X-Plex-Container-Size=20000", token).get("Metadata") or []
    devs = {}
    try:
        devs = {str(d["id"]): d.get("name") or d.get("platform") for d in plex_json("/devices", token).get("Device") or []}
    except Exception:
        pass
    plays = []
    for h in hist:
        if h.get("accountID") != 1:
            continue
        rk = str(h.get("ratingKey")) if h.get("type") == "movie" else (h.get("grandparentKey") or "").rsplit("/", 1)[-1]
        k = rk_to_key.get(rk)
        if not k:
            continue
        plays.append({"title_key": k, "device": str(h.get("deviceID")),
                      "hour": time.localtime(int(h.get("viewedAt") or 0)).tm_hour})
    # labels: is this play SLOT (device x hour) a grown-up slot? kids content = 0, any other content = 1, every
    # not-me tap = 0. (Labelling "rated by him" = 1 instead contrasted 4% of plays against kids titles and called
    # every evening michael - the candidates are all grown-up content, the question is who sits there then.)
    labels = {}
    for m in movies + shows:
        tid = tmdb_guid(m)
        if not tid:
            continue
        k = ("movie:%d" if m.get("type") == "movie" else "tv:%d") % tid
        labels[k] = 0 if household_content(tags(m, "Genre"), m.get("contentRating"), taste.animation_ok) else 1
    for k in notme_keys:
        labels[k] = 0
    ctx = Context(plays, labels, devs)
    best_play = {}
    for p in plays:
        pr = ctx.p(p["device"], p["hour"])
        if p["title_key"] not in best_play or pr > best_play[p["title_key"]][0]:
            best_play[p["title_key"]] = (pr, p)

    lanes = None
    try:
        import couple_compat
        lanes = couple_compat.load_lanes()
    except Exception:
        lanes = None

    # --- score ---
    cands = candidate_sets()
    rated_directors = set()
    for s in taste.seeds + taste.dislikes:
        rated_directors |= s["sets"]["directors"]
    genre_n = collections.Counter()
    for tid, *_ in taste.ratings:
        f = bc.read_json(os.path.join(tc.CACHE, "movie-%d.json" % tid))
        for g in set(tc.norm_genres((f or {}).get("genres"))):
            genre_n[g] += 1
    items, household, counts = [], [], collections.Counter()
    for k, t in titles.items():
        if k in done or t["plex_rated"]:
            counts["answered"] += 1
            continue
        if k in hero:
            counts["hero_drop"] += 1
            continue
        try:
            f = taste.tmdb.details(t["type"], t["tmdb"], tc.STATIC_TTL_D)
        except Exception:
            counts["tmdb_failed"] += 1
            continue
        genres = set(tc.norm_genres(t["genres"])) | set(tc.norm_genres(f.get("genres")))
        why_hh = household_content(genres, t["cr"], taste.animation_ok)
        pc, play = best_play.get(k, (None, None))      # no play in Plex history -> unknown, never penalised
        if not why_hh and play and pc < HIDE_P:
            why_hh = ctx.explain(play["device"], play["hour"])
        match, because, people, parts = taste.score(f)
        guess = te.guess_from(table, match)
        cs = tc.feature_sets(f)
        moves = sum(1 for c in cands if raw_sim(cs, c) >= SIM_THRESH)
        days = int((now - t["last"]) / 86400) if t["last"] else None
        fresh = math.exp(-(days if days is not None else 365) / FRESH_DAYS)
        u_line = max(0.0, 1.0 - abs((guess or 8) - 7.5) / 2.5)
        novelty = 1.0 - parts["sim"]
        uncertainty = max(u_line, novelty)
        new_dirs = [p for p in cs["directors"] if p not in rated_directors and p not in taste.person_w]
        thin = [g for g in genres if genre_n.get(g, 0) < 5 and g not in tc.KIDS]
        coverage = 1.0 if new_dirs else (0.6 if thin else 0.0)
        reasons = []
        her = bool(lanes) and match < 0.55 and any(
            couple_compat.lane_matches(l, set(x.lower() for x in genres), set(a.lower() for a in t["actors"])) for l in lanes)
        row = {
            "key": ("m:" if t["type"] == "movie" else "t:") + t["rk"], "type": t["type"], "rating_key": t["rk"],
            "tmdb_id": t["tmdb"], "title": tc.clip(t["title"], 200), "year": t["year"] if isinstance(t["year"], int) else None,
            "thumb": "/library/metadata/%s/thumb" % t["rk"],
            "watched_at": datetime.date.fromtimestamp(t["last"]).isoformat() if t["last"] else None,
            "days_since": days, "completion": t["completion"], "episodes": t.get("eps"),
            "genres": sorted(genres - tc.KIDS)[:4], "guess": guess, "match": match,
            "context_p": round(pc, 3) if pc is not None else None, "leverage": 0.0, "reasons": reasons, "terms": {},
        }
        if why_hh:
            row["hidden_reason"] = why_hh
            household.append(row)
            counts["household_hidden"] += 1
            continue
        lev = 0.40 * 0.0 + 0.25 * uncertainty + 0.20 * fresh + 0.15 * coverage
        row["terms"] = {"moves": moves, "uncertainty": round(uncertainty, 3), "freshness": round(fresh, 3),
                        "coverage": coverage, "novelty": round(novelty, 3)}
        row["_lev_rest"] = lev
        if t["completion"] is not None:
            reasons.append("you stopped at %d%%" % t["completion"])
        if days is not None and days <= 14:
            reasons.append("watched %s" % ("today" if days == 0 else ("yesterday" if days == 1 else "%d days ago" % days)))
        if new_dirs and t["type"] == "movie":
            reasons.append("first %s film you'd rate" % new_dirs[0])
        elif novelty > 0.75:
            reasons.append("new territory for Cortex")
        elif u_line > 0.8:
            reasons.append("Cortex can't call this one")
        if pc is not None and pc < DOUBT_P:
            reasons.append("maybe household - tap Not me if so")
        elif her:
            reasons.append("maybe hers - rate it if you watched too")
        row["_ctx"] = 1.0 if pc is None else 0.5 + 0.5 * min(1.0, pc / 0.6)
        row["_her"] = 0.7 if her else 1.0
        items.append(row)
    max_moves = max([r["terms"]["moves"] for r in items] + [1])
    for r in items:
        infl = math.log1p(r["terms"]["moves"]) / math.log1p(max_moves)
        r["leverage"] = round(min(1.0, (0.40 * infl + r.pop("_lev_rest")) * r.pop("_ctx") * r.pop("_her")), 3)
        if r["terms"]["moves"] >= 3:
            r["reasons"].insert(0, "moves %d of your picks" % r["terms"]["moves"])
        r["reasons"] = r["reasons"][:3] or ["on your watched list, unrated"]
    for r in household:
        r["reasons"] = [r["hidden_reason"]]
    items.sort(key=lambda r: -r["leverage"])
    household.sort(key=lambda r: -(r.get("context_p") or 0))
    moves_sorted = sorted(r["terms"]["moves"] for r in items)
    median_moves = moves_sorted[len(moves_sorted) // 2] if moves_sorted else 0
    r7, r30, streak = ledger_stats(events, now)
    hi = sum(1 for r in items if r["leverage"] >= HIGH_LEVERAGE)
    data = {
        "backlog": {"total": len(items), "high_leverage": hi, "beyond_high": max(0, hi - sum(1 for r in items[:MAX_ITEMS] if r["leverage"] >= HIGH_LEVERAGE)),
                    "household_hidden": counts["household_hidden"],
                    "bailed": sum(1 for r in items if r["completion"] is not None), "rated_7d": r7, "rated_30d": r30,
                    "streak_days": streak, "median_moves": median_moves},
        "session_cap": SESSION_CAP,
        "items": [{k2: v for k2, v in r.items() if k2 != "hidden_reason"} for r in items[:MAX_ITEMS]],
        "household": [{k2: v for k2, v in r.items() if k2 != "hidden_reason"} for r in household[:MAX_HOUSEHOLD]],
        "context": {"plays_labelled": ctx.n, "prior_grownup": round(ctx.prior, 3)},
        "eval": {"rho": (ev_state.get("current") or {}).get("rho"), "baseline_rho": (ev_state.get("baseline") or {}).get("rho"),
                 "live_mae": ev_state.get("live_mae"), "calibrated": bool(table)},
        "refreshed_at": bc.iso(now),
        "note": ("Titles played on your Plex account that you have not rated, ranked by how much your rating would teach "
                 "Cortex. Household plays (kids titles, and plays whose device + time of day look like the household) are "
                 "hidden but listed. Ratings: %s. %s" % (taste.source, " ".join(taste.notes[:3]))).strip()[:1200],
    }
    write(data)
    log("rate-queue: %d to rate (%d high-leverage, median moves %d), %d household hidden, %d answered, %d hero-drop; "
        "context model %d labelled plays, grown-up prior %.2f; TMDB %d live / %d cached"
        % (len(items), hi, median_moves, counts["household_hidden"], counts["answered"], counts["hero_drop"], ctx.n,
           ctx.prior, taste.tmdb.live_calls, taste.tmdb.cache_hits))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        try:
            if time.time() - os.path.getmtime(LOCK) > (60 if a.quick else 1800):
                os.remove(LOCK)
                return main()
        except OSError:
            pass
        log("busy: another rate_queue run holds %s - skipping (single-flight)" % LOCK)
        return 0
    try:
        os.close(fd)
        return quick() if a.quick else (0 if full() else 1)
    except Exception as ex:
        log("FATAL: %s: %s" % (type(ex).__name__, ex))
        return 1
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
