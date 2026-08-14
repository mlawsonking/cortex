#!/usr/bin/env python3
# gap_radar.py - I6 Gap Radar: "you are N films from completing X".
#
# Two kinds of completion, one question: what is ALMOST finished?
#   AUTEURS    - the 16 auteur loyalties and their curated canonical filmographies already exist in
#                wg\audit\passport.ps1. That table is parsed READ-ONLY and reused as THE definition of what
#                counts as an auteur's canon, so this engine cannot silently disagree with the passport about
#                who Michael follows or which films are canonical.
#   FRANCHISES - Radarr movie objects carry a `collection` {title, tmdbId}. For every collection the library
#                already owns >= 2 (post-year-floor) films of, TMDB is asked how many films that collection
#                actually contains. That >=2 rule is what keeps the call count bounded (a few hundred, weekly).
#
# WHY THE CURATED TMDB IDs ARE NOT TRUSTED (measured 2026-08-14, not assumed):
#   The map is keyed tmdbId => title, and 108 of its 264 ids resolve to a DIFFERENT film than their label:
#   600 is labelled 'Duel' but is Full Metal Jacket, 902 is labelled 'Hook' but is The City of Lost Children,
#   110 is labelled 'Death Proof' but is Three Colors: Red, 4147 is labelled 'Revolutionary Road' but is Road
#   to Perdition. passport.ps1 cannot see this because it prints the CURATED label for a film it fails to find,
#   so a wrong id quietly scores some other movie's ownership under the director's name.
#   Gap Radar therefore matches on the curated TITLE - the actual human judgement in that file - and re-resolves
#   every id from the director's real TMDB directing credits. The bad ids are counted and reported in
#   generated_note, never repaired: passport.ps1 is read-only to this producer, and the fix belongs at the source.
#
# HARD RULE - THE 1987 YEAR FLOOR (memory\cinematic-taste-profile.md): a film released before 1987 is NEVER a gap.
# Pre-1987 films are dropped from totals AND from missing[] on both halves, so "8/10" means "8 of the 10 films
# that could ever count", not "8 of 10 minus some hidden filter". Anything undatable is dropped and counted -
# guessing a year to make a row look complete is exactly the lie this app exists to avoid.
#
# HONEST FAILURE (nothing is better than a plausible-looking lie):
#   * Radarr unreachable                    -> CANNOT TELL, exit 1, write nothing (the old contract ages into
#                                              STALE, which is the truth)
#   * passport.ps1 missing / unparseable    -> CANNOT TELL, exit 1, write nothing
#   * TMDB key missing, or EVERY auteur or
#     EVERY collection lookup failing       -> CANNOT TELL, exit 1 (an empty list would read as "nothing is
#                                              close", a different claim than "I could not check")
#   * ONE director or ONE collection failing -> skipped and counted in generated_note. Never a fabricated total.
#
# ACTIONLESS BY DESIGN (v1): no grab/monitor verb is offered. Adding a verb is its own gate decision.
# Standalone producer, weekly via the user-session task "Gap Radar" (Sun 07:00, pythonw.exe - no console flash,
# exit code still reaches the task-health watchdog). Pure stdlib, pure ASCII source.
import json, os, re, sys, time, datetime, difflib, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
PASSPORT_PS1 = os.path.join(WG, "audit", "passport.ps1")
RADARR = "http://127.0.0.1:7878/api/v3"
YEAR_FLOOR = 1987
TOP_AUTEURS = 12
TOP_FRANCHISES = 12
MAX_MISSING = 5
MIN_OWNED_FOR_LOOKUP = 2          # only ask TMDB about a collection we already own >= 2 films of
TMDB_SLEEP = 0.15
TITLE_MATCH = 0.60                # 'Twelve Monkeys' vs '12 Monkeys' scores 0.64; a wrong film scores far lower
# passport.ps1's key is a two-director credit that no single TMDB person page covers; Joel is credited as
# director on the joint filmography, so he is the lookup handle. The only name alias in this producer.
PERSON_ALIAS = {"Coen Brothers": "Joel Coen"}


def fatal(msg):
    print("CANNOT TELL: %s" % msg)
    print("FATAL: gap-radar NOT written - the previous contract keeps its real age.")
    sys.exit(1)


def tmdb_get(path, key, params=None):
    """One TMDB GET with a single retry. Returns the decoded object, or raises."""
    q = {"api_key": key}
    if params:
        q.update(params)
    url = "https://api.themoviedb.org/3/%s?%s" % (path, urllib.parse.urlencode(q))
    req = urllib.request.Request(url, headers={"User-Agent": "cortex-gap-radar/1.0",
                                               "Accept": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=25))
    except Exception:
        time.sleep(1.0)
        return json.load(urllib.request.urlopen(req, timeout=25))


def norm_title(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def title_score(a, b):
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def parse_filmography(path):
    """Read the curated $FILMOGRAPHY table out of passport.ps1 (READ-ONLY reuse - it is never edited).

    Returns [(director, [(tmdbId, curated_title), ...]), ...] in the file's own order.
    """
    with open(path, encoding="utf-8-sig") as fh:
        src = fh.read()
    try:
        start = src.index("$FILMOGRAPHY = [ordered]@{")
        end = src.index("# Flatten to id lists", start)
    except ValueError:
        raise ValueError("the $FILMOGRAPHY table is no longer where it was in passport.ps1")
    block = src[start:end]
    out = []
    for name, body in re.findall(r"'([^']+)'\s*=\s*\[ordered\]@\{(.*?)\n  \}", block, re.S):
        films, seen = [], set()
        for tid, title in re.findall(r"(\d+)\s*=\s*'((?:[^']|'')*)'", body):
            tid = int(tid)
            if tid in seen:
                continue
            seen.add(tid)
            films.append((tid, title.replace("''", "'")))   # PowerShell escapes ' as ''
        if films:
            out.append((name, films))
    return out


def directing_credits(person_id, key):
    """Every film this person is credited as Director on: {tmdbId: (title, year)}. Undated films are dropped."""
    cr = tmdb_get("person/%d/movie_credits" % person_id, key)
    time.sleep(TMDB_SLEEP)
    out = {}
    for c in (cr.get("crew") or []):
        if (c.get("job") or "") != "Director":
            continue
        mid = c.get("id")
        rd = (c.get("release_date") or "")[:4]
        if not mid or not rd.isdigit():
            continue
        out[int(mid)] = (c.get("title") or c.get("original_title") or "", int(rd))
    return out


def resolve_director(name, labels, key):
    """Find the TMDB person behind a curated director name, and return their directing credits.

    The search result is NOT taken on faith: candidates are scored by how many of the curated canonical titles
    actually appear in their directing credits, so a same-name stranger cannot be adopted silently.
    """
    query = PERSON_ALIAS.get(name, name)
    res = tmdb_get("search/person", key, {"query": query})
    time.sleep(TMDB_SLEEP)
    best, best_hits = None, 0
    for p in (res.get("results") or [])[:3]:
        pid = p.get("id")
        if not pid:
            continue
        try:
            credits = directing_credits(int(pid), key)
        except Exception:
            continue
        titles = [t for t, _ in credits.values()]
        hits = sum(1 for lab in labels if any(title_score(lab, t) >= TITLE_MATCH for t in titles))
        if hits > best_hits:
            best, best_hits = credits, hits
        if best_hits >= 3:              # unambiguous: three canonical titles from the same person
            break
    if best is None or best_hits < 2:
        return None                     # cannot establish this director honestly -> caller skips + counts
    return best


def main():
    # ---- auteur canon (read-only reuse of passport.ps1's curated map) --------------------------------------
    if not os.path.isfile(PASSPORT_PS1):
        fatal("the auteur source %s does not exist - there is no honest auteur list to score against." % PASSPORT_PS1)
    try:
        filmography = parse_filmography(PASSPORT_PS1)
    except Exception as e:
        fatal("could not parse the curated filmography out of passport.ps1 (%s: %s)." % (type(e).__name__, e))
    if not filmography:
        fatal("parsed 0 directors out of passport.ps1 - the $FILMOGRAPHY table shape changed.")

    # ---- Radarr (the ownership truth) ---------------------------------------------------------------------
    try:
        key = open(os.path.join(WG, "radarr.key")).read().strip()
        req = urllib.request.Request(RADARR + "/movie", headers={"X-Api-Key": key})
        movies = json.load(urllib.request.urlopen(req, timeout=180))
    except Exception as e:
        fatal("Radarr at %s is unreachable (%s: %s) - ownership is unknowable without it."
              % (RADARR, type(e).__name__, e))
    if not isinstance(movies, list) or not movies:
        fatal("Radarr returned no movies - refusing to report a 0%% library.")
    by_tmdb = {}
    for m in movies:
        t = m.get("tmdbId")
        if t:
            by_tmdb[int(t)] = m
    owned_ids = set(t for t, m in by_tmdb.items() if m.get("hasFile"))

    kp = os.path.join(WG, "tmdb.key")
    tmdb_key = open(kp).read().strip() if os.path.isfile(kp) else ""
    if not tmdb_key:
        fatal("no TMDB key at %s - neither auteur filmographies nor franchise totals can be checked, and empty "
              "lists would read as 'nothing is close', which is a different claim than 'I could not look'." % kp)

    # ---- AUTEURS ------------------------------------------------------------------------------------------
    auteurs = []
    below_floor = unresolved_total = bad_ids = auteur_films = directors_failed = 0
    for name, films in filmography:
        labels = [t for _, t in films]
        try:
            credits = resolve_director(name, labels, tmdb_key)
        except Exception:
            credits = None
        if not credits:
            directors_failed += 1
            continue
        owned, total, unresolved, missing, used = 0, 0, 0, [], set()
        for curated_id, label in films:
            # the curated TITLE is the canon; the id is re-derived from the director's real credits
            hit, hit_score = None, TITLE_MATCH
            for mid, (mtitle, myear) in credits.items():
                if mid in used:
                    continue
                s = title_score(label, mtitle)
                if s >= hit_score:
                    hit, hit_score = (mid, mtitle, myear), s
            if hit is None:
                unresolved += 1
                continue
            mid, mtitle, myear = hit
            used.add(mid)
            if mid != curated_id:
                bad_ids += 1
            if myear < YEAR_FLOOR:
                below_floor += 1
                continue
            total += 1
            if mid in owned_ids:
                owned += 1
            else:
                rm = by_tmdb.get(mid)
                missing.append({"title": (rm.get("title") if rm else None) or mtitle, "year": myear,
                                "tmdb": mid, "in_radarr": rm is not None})
        if total <= 0:
            continue
        auteur_films += total
        unresolved_total += unresolved
        missing.sort(key=lambda x: (x["year"], x["title"]))
        auteurs.append({"name": name, "owned": owned, "total": total,
                        "pct": int(round(100.0 * owned / total)), "unresolved": unresolved,
                        "missing": missing[:MAX_MISSING]})
    if not auteurs:
        fatal("not one of the %d curated directors could be resolved at TMDB - the auteur half is unknowable "
              "this run." % len(filmography))
    # closest to complete first; already-complete auteurs sink to the bottom (they are not gaps)
    auteurs.sort(key=lambda a: (a["owned"] >= a["total"], -a["pct"], a["total"] - a["owned"], -a["total"]))

    # ---- FRANCHISES ---------------------------------------------------------------------------------------
    cand = {}
    for m in movies:
        c = m.get("collection") or {}
        cid = c.get("tmdbId")
        if not cid or not m.get("hasFile"):
            continue
        y = m.get("year")
        if not isinstance(y, int) or y < YEAR_FLOOR:      # the floor decides candidacy too
            continue
        e = cand.setdefault(int(cid), {"owned": 0, "title": c.get("title") or c.get("name") or ""})
        e["owned"] += 1
    candidates = sorted([cid for cid, e in cand.items() if e["owned"] >= MIN_OWNED_FOR_LOOKUP])

    today = datetime.date.today().isoformat()
    franchises, skipped, unreleased = [], 0, 0
    for cid in candidates:
        try:
            coll = tmdb_get("collection/%d" % cid, tmdb_key)
        except Exception:
            skipped += 1                                   # never fabricate a total
            time.sleep(TMDB_SLEEP)
            continue
        time.sleep(TMDB_SLEEP)
        parts, seen = [], set()
        for p in (coll.get("parts") or []):
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            rd = p.get("release_date") or ""
            if len(rd) < 4 or not rd[:4].isdigit() or rd > today:
                unreleased += 1        # undated, or not out yet: not a gap anyone could close today
                continue
            y = int(rd[:4])
            if y < YEAR_FLOOR:
                below_floor += 1
                continue
            parts.append({"title": p.get("title") or p.get("original_title") or ("tmdb:%d" % pid),
                          "year": y, "tmdb": int(pid)})
        total = len(parts)
        if total < 2:
            continue
        have = [p for p in parts if p["tmdb"] in owned_ids]
        if len(have) == total:
            continue                                       # complete: not a gap
        missing = [dict(p, in_radarr=(p["tmdb"] in by_tmdb)) for p in parts if p["tmdb"] not in owned_ids]
        missing.sort(key=lambda x: (x["year"], x["title"]))
        franchises.append({"name": coll.get("name") or cand[cid]["title"] or ("collection %d" % cid),
                           "tmdb": cid, "owned": len(have), "total": total,
                           "pct": int(round(100.0 * len(have) / total)),
                           "missing": missing[:MAX_MISSING]})
    if candidates and skipped == len(candidates):
        fatal("all %d TMDB collection lookups failed - franchise completion is unknowable this run." % skipped)

    franchises.sort(key=lambda f: (-f["pct"], f["total"] - f["owned"], -f["total"]))
    reported = len(franchises)
    franchises = franchises[:TOP_FRANCHISES]
    auteurs_all = len(auteurs)
    auteurs = auteurs[:TOP_AUTEURS]

    note = ("auteurs: the %d curated loyalties and their canonical title lists in wg\\audit\\passport.ps1, "
            "scored against Radarr hasFile (%d films after the %d year floor). Titles are matched to each "
            "director's real TMDB directing credits because %d of that map's TMDB ids point at a different film "
            "than their label - a bad-id bug at the source, reported here, not repaired here, and it does NOT "
            "propagate into these numbers. %d curated titles matched no credit and %d directors could not be "
            "resolved at all; both are excluded, never guessed. franchises: %d Radarr collections owning >=%d "
            "post-%d films were asked at TMDB how many films they contain; %d came back incomplete, %d skipped "
            "after TMDB errors (never estimated). Excluded everywhere: %d pre-%d films, %d unreleased or undated "
            "entries. owned = a file on disk, so a film merely parked in Radarr still counts as a gap."
            % (len(filmography), auteur_films, YEAR_FLOOR, bad_ids, unresolved_total, directors_failed,
               len(candidates), MIN_OWNED_FOR_LOOKUP, YEAR_FLOOR, reported, skipped, below_floor, YEAR_FLOOR,
               unreleased))

    data = {
        "year_floor": YEAR_FLOOR,
        "auteur_source": "wg\\audit\\passport.ps1 (curated $FILMOGRAPHY titles, read-only; ids re-resolved at TMDB)",
        "auteurs": auteurs,
        "franchises": franchises,
        "totals": {
            "auteurs_tracked": auteurs_all,
            "auteur_films": auteur_films,
            "franchise_candidates": len(candidates),
            "franchises_incomplete": reported,
            "tmdb_collections_skipped": skipped,
            "films_below_floor": below_floor,
            "titles_unresolved": unresolved_total,
            "directors_unresolved": directors_failed,
            "curated_ids_wrong": bad_ids,
        },
        "generated_note": note,
    }
    path = bc.write_contract("gap-radar", data)
    print("gap-radar contract written: %s" % path)
    print("  auteurs: %d/%d resolved (%d films post-floor, %d curated ids were wrong, %d titles unmatched)"
          % (auteurs_all, len(filmography), auteur_films, bad_ids, unresolved_total))
    print("  franchises: %d candidates -> %d incomplete, %d skipped" % (len(candidates), reported, skipped))
    for a in data["auteurs"][:5]:
        gap = a["total"] - a["owned"]
        print("  AUTEUR  %-20s %3d/%-3d %3d%%  %s" % (a["name"], a["owned"], a["total"], a["pct"],
              ("complete" if not gap else "%d to go: %s"
               % (gap, ", ".join(m["title"] for m in a["missing"])))[:96]))
    for f in data["franchises"][:5]:
        gap = f["total"] - f["owned"]
        print("  FRANCH  %-24s %3d/%-3d %3d%%  %d to go: %s"
              % (f["name"][:24], f["owned"], f["total"], f["pct"], gap,
                 ", ".join(m["title"] for m in f["missing"])[:70]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
