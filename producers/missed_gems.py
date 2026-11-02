#!/usr/bin/env python3
# missed_gems.py - page 2 "Missed Gems" (inward): michael's OWN library, taste-matched and UNWATCHED.
# Spec + his locked decision 1 ("this is you, why you no watch yet?"): wg\GAMEPLAN-STREAMING-PAGES-2026-10.md.
#
# Fully deterministic - no model call, so the weekly refresh costs nothing. The `because` lists (the loved titles a
# pick is most similar to) and the match score explain every row, exactly like the Recs card.
#
# SOURCES
#   * FILMS  the unwatched-pool contract (Plex Movies, viewCount 0, not Plex-rated, >= 1987; weekly Sun 06:15).
#   * SHOWS  straight from the Plex TV section: series with ZERO watched episodes. Deliberately NOT by extending
#            unwatched-pool: that contract is a top-level ARRAY of movie rows, and its consumers (couple-compat's
#            Date Night refresh, the retained dead-shelf producer) would read a show row as a film. Reading Plex
#            here is one cheap call and leaves their contract untouched; tv_source in the contract says so.
#   Scoring = taste_core.score over TMDB features (cached under data\cache\tmdb; two-stage so only the ~450 most
#   promising films are ever looked up, gentle on TMDB). A row with no TMDB id is scored on Plex genres + actors.
#
# EXCLUSIONS: taste_core hard rules (1987 floor for films, no kids/family, animation only via his ratings, no
# docu/talk/reality), rated films, anything in Plex watch history, titles on the current Streaming Best page,
# and anything tagged 'hero-drop' (the Marvel/DC drop was curated for Nathaniel, not for michael - shelving it
# here would be the household-pollution error Taste Velocity already proved).
#
# HONEST EXIT: unwatched-pool missing/unreadable, Radarr/Sonarr unreachable, or the ratings seed missing -> exit 1,
# write NOTHING. Plex TV section unreachable -> films only, and tv_source says so (never silently films-only).
# Fewer than MIN_ROWS scored rows -> exit 2 (CANNOT TELL), nothing written.
#
# Weekly task "Missed Gems" Sat 06:50 (pythonw - rc reaches the task-health watchdog).
import datetime, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc
import taste_core as tc

LANDED_DAYS = 60
LANDED_N = 10
GEMS_N = 15
SHOWS_N = 5                 # contract 1.1.0: shows get their own section (films dominate the match ranking)
STAGE2_FILMS = 450
MIN_ROWS = 10
HERO_TAG = "hero-drop"


def log(msg):
    print(msg, flush=True)


def plex_shows(token):
    req = urllib.request.Request("%s/library/sections/2/all?includeGuids=1&X-Plex-Token=%s" % (tc.PLEX, token),
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["MediaContainer"].get("Metadata") or []


def guid(meta, scheme):
    for g in meta.get("Guid") or []:
        gid = g.get("id", "")
        if gid.startswith(scheme + "://"):
            try:
                return int(gid.split("//", 1)[1])
            except ValueError:
                return None
    return None


def pseudo(kind, title, year, genres, actors):
    """Feature dict for a row TMDB cannot (or need not yet) describe: Plex genres + actors, no keywords."""
    return {"kind": kind, "title": title, "year": year, "genres": list(genres or []), "keywords": [],
            "directors": [], "cast": list(actors or []), "vote_average": 0.0, "vote_count": 0}


def row(kind, rk, tmdb, title, year, genres, added, rating, scored, episodes=None):
    match, because, people, _parts = scored
    days = int((time.time() - added) / 86400) if added else None
    return {
        "key": "%s:%s" % ("m" if kind == "movie" else "t", rk), "type": kind, "tmdb_id": tmdb, "title": title or "?",
        "year": year, "genres": tc.norm_genres(genres)[:4], "match": match, "because": because, "people": people,
        "added_at": datetime.date.fromtimestamp(added).isoformat() if added else None,
        "days_on_shelf": max(0, days) if days is not None else None,
        "rating": round(float(rating), 1) if isinstance(rating, (int, float)) else None,
        "rating_key": str(rk), "thumb": "/library/metadata/%s/thumb" % rk, "episodes": episodes,
    }


def main():
    key = tc.api_key("tmdb")
    if not key:
        log("FAILED: no TMDB key at wg\\tmdb.key - nothing written")
        return 1
    env = bc.read_json(os.path.join(bc.DATA, "unwatched-pool.json"))
    pool = env.get("data") if isinstance(env, dict) else None
    if not isinstance(pool, list) or not pool:
        log("FAILED: the unwatched-pool contract is missing or empty - there is no honest film pool; nothing written")
        return 1
    pool_age_d = None
    try:
        pool_age_d = (time.time() - datetime.datetime.fromisoformat(env["_meta"]["generated_at"]).timestamp()) / 86400
    except Exception:
        pass

    taste = tc.Taste(log).build(key)
    tm = taste.tmdb
    _m, _s, _st, radarr_by_tmdb, sonarr_by_tvdb = tc.owned_sets()
    rtag = stag = None
    try:
        rtag = next((t["id"] for t in tc.arr_get(tc.RADARR, "radarr", "/tag") if t.get("label") == HERO_TAG), None)
        stag = next((t["id"] for t in tc.arr_get(tc.SONARR, "sonarr", "/tag") if t.get("label") == HERO_TAG), None)
    except Exception:
        pass
    hero_movies = {t for t, m in radarr_by_tmdb.items() if rtag is not None and rtag in (m.get("tags") or [])}
    hero_shows = {t for t, s in sonarr_by_tvdb.items() if stag is not None and stag in (s.get("tags") or [])}
    token = tc.plex_token()
    watched = tc.watched_titles(token)
    on_page1 = tc.current_ids("streaming-best")
    ex = {"rated": 0, "watched": 0, "rules": 0, "hero_drop": 0, "on_streaming_best": 0, "no_rating_key": 0}

    # ---------------- films: stage 1 cheap prescore on Plex fields, stage 2 TMDB-enriched ----------------
    cutoff = time.time() - LANDED_DAYS * 86400
    cand = []
    for p in pool:
        tmdb = p.get("tmdb")
        if not p.get("ratingKey"):
            ex["no_rating_key"] += 1
            continue
        if tmdb and int(tmdb) in taste.rated_ids:
            ex["rated"] += 1
            continue
        if tmdb and int(tmdb) in hero_movies:
            ex["hero_drop"] += 1
            continue
        if tmdb and ("movie", int(tmdb)) in on_page1:
            ex["on_streaming_best"] += 1
            continue
        if tc.norm_title(p.get("title")) in watched:
            ex["watched"] += 1
            continue
        pf = pseudo("movie", p.get("title"), p.get("year"), p.get("genres"), p.get("actors"))
        if taste.excluded(pf, enforce_floor=True):
            ex["rules"] += 1
            continue
        cand.append((taste.score(pf)[0], p))
    cand.sort(key=lambda x: -x[0])
    stage2 = [p for _, p in cand[:STAGE2_FILMS]] + [p for _, p in cand[STAGE2_FILMS:] if (p.get("addedAt") or 0) >= cutoff]
    rows = []
    for p in stage2:
        tmdb = int(p["tmdb"]) if p.get("tmdb") else None
        f = None
        if tmdb:
            try:
                f = tm.details("movie", tmdb, tc.STATIC_TTL_D)
            except Exception:
                f = None
        if f is None:
            f = pseudo("movie", p.get("title"), p.get("year"), p.get("genres"), p.get("actors"))
        elif taste.excluded(f, enforce_floor=True):            # TMDB genres can reveal a kids/docu lane Plex hid
            ex["rules"] += 1
            continue
        rows.append(row("movie", p["ratingKey"], tmdb, p.get("title"), p.get("year"), p.get("genres"),
                        p.get("addedAt"), p.get("rating"), taste.score(f)))
    n_films = len(cand)

    # ---------------- shows: Plex TV section, never-started series ----------------
    tv_source = "Plex TV section (series with zero watched episodes), read directly - unwatched-pool is films-only"
    n_shows = 0
    try:
        shows = plex_shows(token)
    except Exception as e:
        shows = None
        tv_source = "Plex TV section UNREACHABLE this run (%s) - this week's page is FILMS ONLY" % type(e).__name__
    for s in shows or []:
        if (s.get("viewedLeafCount") or 0) > 0:
            continue
        tvdb, tmdb = guid(s, "tvdb"), guid(s, "tmdb")
        if tvdb and tvdb in hero_shows:
            ex["hero_drop"] += 1
            continue
        if tmdb and ("tv", tmdb) in on_page1:
            ex["on_streaming_best"] += 1
            continue
        if tc.norm_title(s.get("title")) in watched:
            ex["watched"] += 1
            continue
        genres = [g.get("tag") for g in s.get("Genre") or [] if g.get("tag")]
        actors = [r.get("tag") for r in s.get("Role") or [] if r.get("tag")]
        f = None
        if tmdb:
            try:
                f = tm.details("tv", tmdb, tc.STATIC_TTL_D)
            except Exception:
                f = None
        if f is None:
            f = pseudo("tv", s.get("title"), s.get("year"), genres, actors)
        if taste.excluded(f, enforce_floor=False) or taste.excluded(pseudo("tv", "", None, genres, []), enforce_floor=False):
            ex["rules"] += 1
            continue
        n_shows += 1
        rows.append(row("tv", s.get("ratingKey"), tmdb, s.get("title"), s.get("year"), genres, s.get("addedAt"),
                        s.get("audienceRating") or s.get("rating"), taste.score(f), episodes=s.get("leafCount")))

    log("scored %d rows (%d films prescored, %d enriched; %d shows) | excluded %s | TMDB %d live / %d cached / %d failed"
        % (len(rows), n_films, len(stage2), n_shows, json.dumps(ex), tm.live_calls, tm.cache_hits, tm.failures))
    if len(rows) < MIN_ROWS:
        log("CANNOT TELL: only %d scored rows (need %d) - nothing written" % (len(rows), MIN_ROWS))
        return 2

    rows.sort(key=lambda r: (-r["match"], r["title"]))
    landed = [r for r in rows if r["days_on_shelf"] is not None and r["days_on_shelf"] <= LANDED_DAYS][:LANDED_N]
    taken = {r["key"] for r in landed}
    gems = [r for r in rows if r["key"] not in taken][:GEMS_N]
    taken |= {r["key"] for r in gems}
    # 1.1.0: the first run scored 79 never-started series and NONE reached the film-dominated top lists, so a page
    # promised as "shows and movies" read films-only without saying so. Shows now get their own top-5 section.
    shows_top = [r for r in rows if r["type"] == "tv" and r["key"] not in taken][:SHOWS_N]

    note = ("Your own library, never played. Films: the unwatched-pool contract (%s); shows: %s. Match = similarity "
            "to the films you rated 8+ and the series you binge (TMDB keywords + shared directors/cast, scaled by "
            "genre overlap) + your genre weights + director/cast affinity + quality. Excluded: anything rated or in "
            "Plex watch history, kids/family lanes, docu/talk/reality, pre-1987 films, the hero-drop titles added "
            "for Nathaniel, and titles on this month's Streaming Best page."
            % ("%.1f days old" % pool_age_d if pool_age_d is not None else "age unknown", tv_source.split(" (")[0]))
    if pool_age_d is not None and pool_age_d > 8:
        note += " WARNING: the film pool is past its 8-day SLO - recently watched films may still appear."
    note += " Ratings: %s (%d)." % ("your ratings + the taste loop" if taste.source == "ratings-effective"
                                   else "the frozen Trakt snapshot", len(taste.ratings))
    if taste.notes:
        note += " Caveats: " + "; ".join(taste.notes) + "."
    data = {"landed_days": LANDED_DAYS, "tv_source": tv_source,
            "counts": {"movies_pool": len(pool), "shows_pool": n_shows, "scored": len(rows), "excluded": ex},
            "landed": landed, "gems": gems, "shows": shows_top, "note": note}
    path = bc.write_contract("missed-gems", data)
    log("missed-gems written: %s (%d landed in %dd, %d gems, %d shows of %d considered)"
        % (path, len(landed), LANDED_DAYS, len(gems), len(shows_top), n_shows))
    for label, lst in (("LANDED", landed), ("GEMS", gems), ("SHOWS", shows_top)):
        for r in lst:
            log("  %-6s [%s] %s (%s) match %.2f  %sd on shelf  because %s"
                % (label, "film" if r["type"] == "movie" else "show", r["title"], r["year"], r["match"],
                   r["days_on_shelf"], ", ".join(r["because"]) or "-"))
    return 0


if __name__ == "__main__":
    try:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s - nothing written" % (type(e).__name__, e))
        sys.exit(1)
